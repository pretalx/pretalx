# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.views.generic import FormView

from pretalx.common.security import session_reauth
from pretalx.common.text.phrases import phrases
from pretalx.common.views.generic import GenericLoginView, GenericResetView
from pretalx.common.views.redirect import build_login_redirect_url
from pretalx.common.views.verification import GenericVerificationView, GenericVerifyView
from pretalx.person.domain.user import change_password_after_reset
from pretalx.person.interfaces.forms import ReauthForm, RecoverForm, ResetForm
from pretalx.person.models import User


class LoginView(GenericLoginView):
    template_name = "orga/auth/login.html"
    orga = True

    @cached_property
    def success_url(self):
        if self.event:
            return self.event.orga_urls.base
        return reverse("orga:event.list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["hide_register"] = True
        return kwargs

    def get_password_reset_link(self):
        if self.event:
            return reverse("orga:event.auth.reset", kwargs={"event": self.event.slug})
        return reverse("orga:auth.reset")


class ReauthView(FormView):
    template_name = "orga/auth/reauth.html"
    form_class = ReauthForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        session_reauth(self.request)
        return super().form_valid(form)

    def get_success_url(self):
        return GenericLoginView.get_next_url_or_fallback(
            self.request, reverse("orga:event.list")
        )


def logout_view(request):
    if request.method == "POST":
        logout(request)
    return redirect(
        GenericLoginView.get_next_url_or_fallback(request, reverse("orga:login"))
    )


class VerificationView(GenericVerificationView):
    template_name = "orga/auth/verification.html"
    orga = True

    def get_verified_url(self):
        return reverse("orga:event.list")


class VerifyView(GenericVerifyView):
    template_name = "orga/auth/verify.html"

    def get_success_url(self, user):
        target = reverse("orga:event.list")
        if self.request.user == user:
            return self.request.session.pop("verification_next", None) or target
        return build_login_redirect_url(None, target)

    def get_verification_page_url(self):
        return reverse("orga:auth.verification")

    def get_account_settings_url(self):
        return reverse("orga:user.view")


class ResetView(GenericResetView):
    template_name = "orga/auth/reset.html"
    form_class = ResetForm

    def get_success_url(self):
        if getattr(self.request, "event", None):
            return reverse(
                "orga:event.login", kwargs={"event": self.request.event.slug}
            )
        return reverse("orga:login")


class RecoverView(FormView):
    template_name = "orga/auth/recover.html"
    form_class = RecoverForm

    def __init__(self, **kwargs):
        self.user = None
        super().__init__(**kwargs)

    def get_user(self):
        return User.objects.get(
            pw_reset_token=self.kwargs.get("token"),
            pw_reset_time__gte=now() - dt.timedelta(days=1),
        )

    def token_invalid(self):
        messages.error(self.request, phrases.cfp.auth_reset_fail)
        return redirect(reverse("orga:auth.reset"))

    def dispatch(self, request, *args, **kwargs):
        try:
            self.user = self.get_user()
        except User.DoesNotExist:
            return self.token_invalid()
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.user
        return kwargs

    def form_valid(self, form):
        if not change_password_after_reset(
            self.kwargs.get("token"), form.cleaned_data["password"]
        ):
            return self.token_invalid()
        messages.success(self.request, phrases.cfp.auth_reset_success)
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("orga:login")
