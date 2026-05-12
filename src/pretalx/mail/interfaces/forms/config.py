# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from pretalx.common.forms.mixins import (
    JsonSubfieldMixin,
    PretalxI18nFormMixin,
    ReadOnlyFlag,
)
from pretalx.common.forms.widgets import MarkdownWidget, PasswordInput

ENCRYPTED_PASSWORD_PLACEHOLDER = "*" * 24


class MailSettingsForm(
    ReadOnlyFlag, PretalxI18nFormMixin, JsonSubfieldMixin, forms.Form
):
    reply_to = forms.EmailField(
        label=_("Contact address"),
        help_text=_(
            "Reply-To address. If this setting is empty and you have no custom sender, your event email address will be used as Reply-To address."
        ),
        required=False,
    )
    subject_prefix = forms.CharField(
        label=_("Email subject prefix"),
        help_text=_(
            "The prefix will be prepended to outgoing email subjects in [brackets]."
        ),
        required=False,
    )
    signature = forms.CharField(
        label=_("Email signature"),
        help_text=str(
            _("The signature will be added to outgoing emails, preceded by “-- ”.")
        ),
        required=False,
        widget=MarkdownWidget,
    )
    smtp_use_custom = forms.BooleanField(
        label=_("Use custom SMTP server"),
        help_text=_(
            "All email related to your event will be sent over the SMTP server specified by you."
        ),
        required=False,
    )
    mail_from = forms.EmailField(
        label=_("Sender address"),
        help_text=_("Sender address for outgoing emails."),
        required=False,
    )
    smtp_host = forms.CharField(label=_("Hostname"), required=False)
    smtp_port = forms.IntegerField(label=_("Port"), required=False)
    smtp_username = forms.CharField(label=_("Username"), required=False)
    smtp_password = forms.CharField(
        label=_("Password"),
        required=False,
        widget=PasswordInput(attrs={"autocomplete": "new-password"}, render_value=True),
        validators=[
            RegexValidator(
                r"^[A-Za-z0-9!\"#$%&'()*+,./:;<=>?@\^_`{}|~-]+$",
                message=format_lazy(
                    _(
                        "The password contains unsupported letters. Please only use characters "
                        "A-Z, a-z, 0-9, and common special characters ({characters})."
                    ),
                    characters=r'!"#$%%&\'()*+,-./:;<=>?@\^_`{}|~',
                ),
            )
        ],
    )
    smtp_use_tls = forms.BooleanField(
        label=_("Use STARTTLS"),
        help_text=_("Commonly enabled on port 587."),
        required=False,
    )
    smtp_use_ssl = forms.BooleanField(
        label=_("Use SSL"), help_text=_("Commonly enabled on port 465."), required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.fields["smtp_password"].initial:
            self.fields["smtp_password"].initial = ENCRYPTED_PASSWORD_PLACEHOLDER

    def clean(self):
        data = self.cleaned_data
        if not data.get("smtp_use_custom"):
            # We don't need to validate all the rest when we don't use a custom email server
            return data

        if data.get("smtp_username"):
            # Leave password unchanged if the username is set and the password field is empty
            # or contains the encrypted password placeholder.
            # This makes it impossible to set an empty password as long as a username is set, but
            # Python's smtplib does not support password-less schemes anyway.
            password = data.get("smtp_password")
            if not password or password == ENCRYPTED_PASSWORD_PLACEHOLDER:
                data["smtp_password"] = self.initial.get("smtp_password")

        if not data.get("mail_from"):
            self.add_error(
                "mail_from",
                ValidationError(
                    _(
                        "You have to provide a sender address if you use a custom SMTP server."
                    )
                ),
            )
        if data.get("smtp_use_tls") and data.get("smtp_use_ssl"):
            self.add_error(
                "smtp_use_tls",
                ValidationError(
                    _(
                        "You can activate either SSL or STARTTLS security, but not both at the same time."
                    )
                ),
            )
        uses_encryption = data.get("smtp_use_tls") or data.get("smtp_use_ssl")
        localhost_names = [
            "127.0.0.1",
            "::1",
            "[::1]",
            "localhost",
            "localhost.localdomain",
        ]
        if not uses_encryption and data.get("smtp_host") not in localhost_names:
            self.add_error(
                "smtp_host",
                ValidationError(
                    _(
                        "You have to activate either SSL or STARTTLS security if you use a non-local mailserver due to data protection reasons. "
                        "Your administrator can add an instance-wide bypass. If you use this bypass, please also adjust your Privacy Policy."
                    )
                ),
            )

    class Media:
        js = [forms.Script("orga/js/forms/mail.js", defer="")]

    class Meta:
        json_fields = {
            "reply_to": "mail_settings",
            "subject_prefix": "mail_settings",
            "signature": "mail_settings",
            "smtp_use_custom": "mail_settings",
            "mail_from": "mail_settings",
            "smtp_host": "mail_settings",
            "smtp_port": "mail_settings",
            "smtp_username": "mail_settings",
            "smtp_password": "mail_settings",
            "smtp_use_tls": "mail_settings",
            "smtp_use_ssl": "mail_settings",
        }
