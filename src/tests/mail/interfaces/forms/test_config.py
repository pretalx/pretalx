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


def test_mailsettingsform_valid_without_custom_smtp():
    event = EventFactory()
    data = _build_mail_form_data()
    form = MailSettingsForm(data=data, obj=event)

    assert form.is_valid(), form.errors


def test_mailsettingsform_custom_smtp_requires_mail_from():
    event = EventFactory()
    data = _build_mail_form_data(
        smtp_use_custom=True, smtp_host="localhost", smtp_port="587"
    )
    form = MailSettingsForm(data=data, obj=event)

    assert not form.is_valid()
    assert "mail_from" in form.errors


def test_mailsettingsform_custom_smtp_tls_and_ssl_conflict():
    event = EventFactory()
    data = _build_mail_form_data(
        smtp_use_custom=True,
        mail_from="sender@example.com",
        smtp_host="mail.example.com",
        smtp_port="587",
        smtp_use_tls=True,
        smtp_use_ssl=True,
    )
    form = MailSettingsForm(data=data, obj=event)

    assert not form.is_valid()
    assert "smtp_use_tls" in form.errors


def test_mailsettingsform_custom_smtp_non_local_requires_encryption():
    event = EventFactory()
    data = _build_mail_form_data(
        smtp_use_custom=True,
        mail_from="sender@example.com",
        smtp_host="mail.remote.org",
        smtp_port="587",
    )
    form = MailSettingsForm(data=data, obj=event)

    assert not form.is_valid()
    assert "smtp_host" in form.errors


@pytest.mark.parametrize(
    "host",
    ("localhost", "127.0.0.1", "::1", "[::1]", "localhost.localdomain"),
    ids=("localhost", "ipv4_loopback", "ipv6_loopback", "ipv6_bracket", "fqdn"),
)
def test_mailsettingsform_custom_smtp_localhost_no_encryption_ok(host):
    event = EventFactory()
    data = _build_mail_form_data(
        smtp_use_custom=True,
        mail_from="sender@example.com",
        smtp_host=host,
        smtp_port="587",
    )
    form = MailSettingsForm(data=data, obj=event)

    assert form.is_valid(), form.errors


@pytest.mark.parametrize(
    ("use_tls", "use_ssl", "port"),
    ((True, False, "587"), (False, True, "465")),
    ids=("tls", "ssl"),
)
def test_mailsettingsform_custom_smtp_with_encryption_valid(use_tls, use_ssl, port):
    event = EventFactory()
    data = _build_mail_form_data(
        smtp_use_custom=True,
        mail_from="sender@example.com",
        smtp_host="mail.remote.org",
        smtp_port=port,
        smtp_use_tls=use_tls,
        smtp_use_ssl=use_ssl,
    )
    form = MailSettingsForm(data=data, obj=event)

    assert form.is_valid(), form.errors


def test_mailsettingsform_password_placeholder_on_existing():
    event = EventFactory(mail_settings={"smtp_password": "s3cret"})
    form = MailSettingsForm(obj=event)

    assert form.fields["smtp_password"].initial == ENCRYPTED_PASSWORD_PLACEHOLDER


def test_mailsettingsform_password_preserved_when_placeholder_submitted():
    event = EventFactory(mail_settings={"smtp_password": "s3cret"})
    data = _build_mail_form_data(
        smtp_use_custom=True,
        mail_from="sender@example.com",
        smtp_host="localhost",
        smtp_port="587",
        smtp_username="user",
        smtp_password=ENCRYPTED_PASSWORD_PLACEHOLDER,
    )
    form = MailSettingsForm(data=data, obj=event, initial={"smtp_password": "s3cret"})
    form.is_valid()

    assert form.cleaned_data["smtp_password"] == "s3cret"


def test_mailsettingsform_password_preserved_when_empty_with_username():
    event = EventFactory(mail_settings={"smtp_password": "s3cret"})
    data = _build_mail_form_data(
        smtp_use_custom=True,
        mail_from="sender@example.com",
        smtp_host="localhost",
        smtp_port="587",
        smtp_username="user",
        smtp_password="",
    )
    form = MailSettingsForm(data=data, obj=event, initial={"smtp_password": "s3cret"})
    form.is_valid()

    assert form.cleaned_data["smtp_password"] == "s3cret"


def test_mailsettingsform_password_placeholder_without_username_passes_through():
    event = EventFactory(mail_settings={"smtp_password": "s3cret"})
    data = _build_mail_form_data(
        smtp_use_custom=True,
        mail_from="sender@example.com",
        smtp_host="localhost",
        smtp_port="587",
        smtp_username="",
        smtp_password=ENCRYPTED_PASSWORD_PLACEHOLDER,
    )
    form = MailSettingsForm(data=data, obj=event)
    form.is_valid()

    assert form.cleaned_data["smtp_password"] == ENCRYPTED_PASSWORD_PLACEHOLDER


def test_mailsettingsform_new_password_with_username_accepted():
    event = EventFactory()
    data = _build_mail_form_data(
        smtp_use_custom=True,
        mail_from="sender@example.com",
        smtp_host="localhost",
        smtp_port="587",
        smtp_username="user",
        smtp_password="newRealP4ss!",
    )
    form = MailSettingsForm(data=data, obj=event, initial={"smtp_password": "oldpass"})
    form.is_valid()

    assert form.cleaned_data["smtp_password"] == "newRealP4ss!"


def test_mailsettingsform_read_only_disables_fields():
    event = EventFactory()
    form = MailSettingsForm(obj=event, read_only=True)

    for field in form.fields.values():
        assert field.disabled is True
