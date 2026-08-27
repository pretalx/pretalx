# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.core.mail import InvalidMailer, mailers
from django.core.mail.backends.smtp import EmailBackend
from django.test import override_settings

pytestmark = pytest.mark.unit

SMTP_OPTIONS = {
    "host": "mail.example.org",
    "port": "587",
    "username": "user",
    "password": "pass",
    "use_tls": True,
    "use_ssl": False,
}


class SMTPSubclassBackend(EmailBackend):
    """Stand-in for a plugin email backend."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.configured_host = self.host


@pytest.mark.parametrize(
    "backend",
    (
        "django.core.mail.backends.smtp.EmailBackend",
        "tests.common.settings.test_mailers.SMTPSubclassBackend",
    ),
)
def test_smtp_capable_backend_is_configured_from_the_mail_section(backend):
    with override_settings(
        MAILERS={"default": {"BACKEND": backend, "OPTIONS": SMTP_OPTIONS}}
    ):
        assert mailers.default.host == "mail.example.org"


def test_smtp_capable_backend_without_options_cannot_be_built():
    with (
        override_settings(
            MAILERS={
                "default": {
                    "BACKEND": "tests.common.settings.test_mailers.SMTPSubclassBackend"
                }
            }
        ),
        pytest.raises(InvalidMailer, match="OPTIONS must define 'host'"),
    ):
        mailers.default  # noqa: B018 -- building the mailer is the assertion


@pytest.mark.parametrize(
    "backend",
    (
        "django.core.mail.backends.console.EmailBackend",
        "django.core.mail.backends.locmem.EmailBackend",
        "django.core.mail.backends.dummy.EmailBackend",
    ),
)
def test_django_non_smtp_backend_rejects_the_mail_section(backend):
    with (
        override_settings(
            MAILERS={"default": {"BACKEND": backend, "OPTIONS": SMTP_OPTIONS}}
        ),
        pytest.raises(InvalidMailer, match="Unknown options"),
    ):
        mailers.default  # noqa: B018 -- building the mailer is the assertion

    with override_settings(MAILERS={"default": {"BACKEND": backend}}):
        assert mailers.default
