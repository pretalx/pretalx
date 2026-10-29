# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.mail.interfaces.forms import (
    ENCRYPTED_PASSWORD_PLACEHOLDER,
    MailSettingsForm,
)
from tests.factories import EventFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _build_mail_form_data(**overrides):
    data = {
        "reply_to": "",
        "subject_prefix": "",
        "signature": "",
        "smtp_use_custom": "",
        "mail_from": "",
        "smtp_host": "",
        "smtp_port": "587",
        "smtp_username": "",
        "smtp_password": "",
        "smtp_use_tls": "",
        "smtp_use_ssl": "",
    }
    data.update(overrides)
    return data


_CUSTOM = {"smtp_use_custom": True, "mail_from": "sender@example.com"}


@pytest.mark.parametrize(
    ("overrides", "errors"),
    (
        ({}, []),
        ({"smtp_use_custom": True, "smtp_host": "localhost"}, ["mail_from"]),
        ({**_CUSTOM, "smtp_host": "", "smtp_use_tls": True}, ["smtp_host"]),
        (
            {
                **_CUSTOM,
                "smtp_host": "mail.example.com",
                "smtp_use_tls": True,
                "smtp_use_ssl": True,
            },
            ["smtp_use_tls"],
        ),
        ({**_CUSTOM, "smtp_host": "mail.remote.org"}, ["smtp_host"]),
        ({**_CUSTOM, "smtp_host": "localhost"}, []),
        ({**_CUSTOM, "smtp_host": "127.0.0.1"}, []),
        ({**_CUSTOM, "smtp_host": "::1"}, []),
        ({**_CUSTOM, "smtp_host": "[::1]"}, []),
        ({**_CUSTOM, "smtp_host": "localhost.localdomain"}, []),
        ({**_CUSTOM, "smtp_host": "mail.remote.org", "smtp_use_tls": True}, []),
        (
            {
                **_CUSTOM,
                "smtp_host": "mail.remote.org",
                "smtp_port": "465",
                "smtp_use_ssl": True,
            },
            [],
        ),
    ),
    ids=(
        "no_custom_smtp",
        "custom_requires_mail_from",
        "custom_requires_host",
        "tls_and_ssl_conflict",
        "remote_requires_encryption",
        "localhost",
        "ipv4_loopback",
        "ipv6_loopback",
        "ipv6_bracket",
        "fqdn",
        "remote_tls",
        "remote_ssl",
    ),
)
def test_mailsettingsform_validates_custom_smtp(overrides, errors):
    form = MailSettingsForm(data=_build_mail_form_data(**overrides), obj=EventFactory())

    assert form.is_valid() == (not errors), form.errors
    assert list(form.errors) == errors


def test_mailsettingsform_unbound_shows_password_placeholder_and_read_only_disables():
    event = EventFactory(mail_settings={"smtp_password": "s3cret"})
    form = MailSettingsForm(obj=event, read_only=True)

    assert form.fields["smtp_password"].initial == ENCRYPTED_PASSWORD_PLACEHOLDER
    assert all(field.disabled for field in form.fields.values())


@pytest.mark.parametrize(
    ("use_custom", "username", "submitted", "expected"),
    (
        (True, "user", ENCRYPTED_PASSWORD_PLACEHOLDER, "s3cret"),
        (True, "user", "", "s3cret"),
        (True, "", ENCRYPTED_PASSWORD_PLACEHOLDER, "s3cret"),
        (True, "", "", ""),
        (True, "user", "newRealP4ss!", "newRealP4ss!"),
        (False, "user", ENCRYPTED_PASSWORD_PLACEHOLDER, "s3cret"),
    ),
    ids=(
        "placeholder_with_username",
        "empty_with_username",
        "placeholder_without_username",
        "cleared_without_username",
        "changed",
        "no_custom_smtp_placeholder",
    ),
)
def test_mailsettingsform_stored_password_handling(
    use_custom, username, submitted, expected
):
    event = EventFactory(mail_settings={"smtp_password": "s3cret"})
    data = _build_mail_form_data(
        smtp_use_custom=use_custom,
        mail_from="sender@example.com",
        smtp_host="localhost",
        smtp_port="587",
        smtp_username=username,
        smtp_password=submitted,
    )
    form = MailSettingsForm(data=data, obj=event)

    assert form.is_valid(), form.errors
    assert form.cleaned_data["smtp_password"] == expected
