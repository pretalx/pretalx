# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from pretalx.common.forms.fields import NewPasswordConfirmationField, NewPasswordField
from pretalx.common.forms.widgets import PasswordInput
from pretalx.common.text.phrases import phrases
from pretalx.person.models import User


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

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.exclude(pk=self.user.pk).filter(email__iexact=email).exists():
            raise ValidationError(_("Please choose a different email address."))
        return email

    def clean(self):
        data = super().clean()
        password = data.get("password")
        if password and password != data.get("password_repeat"):
            self.add_error(
                "password_repeat", ValidationError(phrases.base.passwords_differ)
            )
        return data

    def save(self):
        if "email" in self.changed_data:
            self.user.change_email(self.cleaned_data.get("email"))
        password = self.cleaned_data.get("password")
        if password:
            self.user.change_password(password)
