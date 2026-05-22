# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import ipaddress

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import check_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils.functional import cached_property
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from pretalx.cfp.forms import CfPFormMixin
from pretalx.common.forms.fields import NewPasswordConfirmationField, NewPasswordField
from pretalx.common.forms.renderers import InlineFormLabelRenderer, InlineFormRenderer
from pretalx.common.forms.widgets import PasswordInput
from pretalx.common.text.phrases import phrases
from pretalx.person.domain.user import change_email, change_password, create_user
from pretalx.person.models import User
from pretalx.person.validators import validate_email_unique

LOGIN_RATE_LIMIT_THRESHOLD = 10
LOGIN_RATE_LIMIT_WINDOW = 300  # seconds


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class LoginInfoForm(forms.Form):
    email = User._meta.get_field("email").formfield()
    old_password = forms.CharField(
        widget=PasswordInput, label=_("Password (current)"), required=True
    )
    password = NewPasswordField(label=phrases.base.new_password, required=False)
    password_repeat = NewPasswordConfirmationField(
        label=phrases.base.password_repeat, required=False, confirm_with="password"
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        kwargs.setdefault("initial", {}).setdefault("email", user.email)
        super().__init__(*args, **kwargs)

    def clean_old_password(self):
        old_pw = self.cleaned_data.get("old_password")
        if not check_password(old_pw, self.user.password):
            raise forms.ValidationError(
                _("The current password you entered was not correct."),
                code="pw_current_wrong",
            )
        return old_pw

    def clean(self):
        data = super().clean()
        password = data.get("password")
        if password and password != data.get("password_repeat"):
            self.add_error(
                "password_repeat", ValidationError(phrases.base.passwords_differ)
            )
        if email := data.get("email"):
            validate_email_unique(email, exclude_user=self.user)
        return data

    def save(self):
        if "email" in self.changed_data:
            change_email(self.user, self.cleaned_data.get("email"))
        password = self.cleaned_data.get("password")
        if password:
            change_password(self.user, password)


class UserForm(CfPFormMixin, forms.Form):
    """Combined login + register form used on every public auth surface
    (CfP flow, generic login view, team-invitation acceptance).

    Registration delegates to :func:`pretalx.person.domain.user.create_user`,
    which runs ``User.clean`` so the email-uniqueness invariant is
    enforced consistently across forms, invitations, and management
    commands.
    """

    default_renderer = InlineFormLabelRenderer
    template_name = "common/forms/auth.html"
    error_messages = {
        "rate_limit": _(
            "For security reasons, please wait 5 minutes before you try again."
        )
    }

    login_email = forms.EmailField(
        max_length=60,
        label=phrases.base.enter_email,
        required=False,
        widget=forms.EmailInput(attrs={"autocomplete": "username"}),
    )
    login_password = forms.CharField(
        label=_("Password"),
        required=False,
        widget=PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    register_name = forms.CharField(
        label=_("Name") + f" ({_('display name')})",
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "name"}),
    )
    register_email = forms.EmailField(
        label=phrases.base.enter_email,
        required=False,
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )
    register_password = NewPasswordField(label=_("Password"), required=False)
    register_password_repeat = NewPasswordConfirmationField(
        label=_("Password (again)"), required=False, confirm_with="register_password"
    )

    FIELDS_ERROR = _(
        "Please fill all fields of either the login or the registration form."
    )

    def __init__(
        self,
        *args,
        request=None,
        hide_login=False,
        hide_register=False,
        no_buttons=False,
        password_reset_link=None,
        success_url=None,
        **kwargs,
    ):
        kwargs.pop("event", None)
        self.request = request
        self.hide_login = hide_login
        self.hide_register = hide_register
        self.no_buttons = no_buttons
        self.password_reset_link = password_reset_link
        self.success_url = success_url
        super().__init__(*args, **kwargs)

    def get_context(self):
        context = super().get_context()
        context["hide_login"] = self.hide_login
        context["hide_register"] = self.hide_register
        context["no_buttons"] = self.no_buttons
        context["password_reset_link"] = self.password_reset_link
        context["success_url"] = self.success_url
        return context

    def render(self, template_name=None, context=None, renderer=None):
        # Override to pass request to the renderer, so that request context
        # processors (request, phrases, etc.) are available in the template.
        renderer = renderer or self.default_renderer
        template_name = template_name or self.template_name
        if context is None:
            context = self.get_context()
        return mark_safe(renderer.render(template_name, context, request=self.request))  # noqa: S308  -- Django template renderer output

    @cached_property
    def ratelimit_key(self):
        if not self.request:
            return None
        if not (ip := get_client_ip(self.request)):
            return None
        try:
            ip_address = ipaddress.ip_address(ip)
        except ValueError:
            return None
        if ip_address.is_private:
            # This can indicate a misconfigured reverse proxy, so we skip
            # rate limiting in this case to avoid blocking innocent users
            return None
        return f"pretalx_login_{ip_address}"

    def _clean_login(self, data):
        try:
            uname = User.objects.get(email__iexact=data.get("login_email")).email
        except User.DoesNotExist:  # We do this to avoid timing attacks
            uname = "user@invalid"

        user = authenticate(username=uname, password=data.get("login_password"))

        if user is None:
            if self.ratelimit_key:
                try:
                    cache.incr(self.ratelimit_key)
                except ValueError:
                    cache.set(self.ratelimit_key, 1, LOGIN_RATE_LIMIT_WINDOW)
            raise ValidationError(
                _(
                    "No user account matches the entered credentials. "
                    "Are you sure that you typed your password correctly?"
                )
            )

        if not user.is_active:
            raise ValidationError(_("Sorry, your account is currently disabled."))

        return data | {"user_id": user.pk}

    def _clean_register(self, data):
        if data.get("register_password") != data.get("register_password_repeat"):
            self.add_error(
                "register_password_repeat",
                ValidationError(phrases.base.passwords_differ),
            )
        try:
            validate_email_unique(data.get("register_email"))
        except ValidationError:
            self.add_error(
                "register_email",
                ValidationError(
                    _(
                        "We already have a user with that email address. Did you already register "
                        "before and just need to log in?"
                    )
                ),
            )
        return data

    def clean(self):
        data = super().clean()

        if data.get("login_email") and data.get("login_password"):
            if (
                self.ratelimit_key
                and (cache.get(self.ratelimit_key) or 0) > LOGIN_RATE_LIMIT_THRESHOLD
            ):
                raise ValidationError(
                    self.error_messages["rate_limit"], code="rate_limit"
                )
            data = self._clean_login(data)
        elif (
            data.get("register_email")
            and data.get("register_password")
            and data.get("register_name")
        ):
            data = self._clean_register(data)
        else:
            raise ValidationError(self.FIELDS_ERROR)

        return data

    def save(self):
        data = self.cleaned_data
        if user_id := data.get("user_id"):
            return user_id

        user = create_user(
            email=data["register_email"],
            name=data["register_name"],
            password=data["register_password"],
        )
        data["user_id"] = user.pk
        return user.pk

    class Media:
        css = {"all": ["common/css/forms/auth.css"]}


class ResetForm(forms.Form):
    default_renderer = InlineFormLabelRenderer

    login_email = forms.EmailField(
        max_length=60, label=phrases.base.enter_email, required=True
    )

    def clean(self):
        data = super().clean()
        try:
            user = User.objects.get(email__iexact=data.get("login_email"))
        except User.DoesNotExist:
            user = None

        data["user"] = user
        return data


class RecoverForm(forms.Form):
    default_renderer = InlineFormRenderer

    email = forms.EmailField(
        label=phrases.base.enter_email,
        widget=forms.EmailInput(
            attrs={"autocomplete": "username", "readonly": "readonly"}
        ),
        required=False,
    )
    password = NewPasswordField(label=phrases.base.new_password, required=False)
    password_repeat = NewPasswordConfirmationField(
        label=phrases.base.password_repeat, required=False, confirm_with="password"
    )

    def __init__(self, *args, user=None, **kwargs):
        if user is not None:
            kwargs.setdefault("initial", {})
            kwargs["initial"]["email"] = user.email
        super().__init__(*args, **kwargs)

    def clean(self):
        data = super().clean()
        if data.get("password") != data.get("password_repeat"):
            self.add_error(
                "password_repeat", ValidationError(phrases.base.passwords_differ)
            )
        return data
