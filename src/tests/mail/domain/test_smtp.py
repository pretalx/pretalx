# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import socket
from unittest.mock import patch

import pytest
from django_scopes import scopes_disabled

from pretalx.common.exceptions import SendMailException
from pretalx.mail.domain.smtp import deliver_persisted, mail_backend_for_event
from pretalx.mail.smtp import CustomSMTPBackend
from tests.factories import QueuedMailFactory, SpeakerFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_mail_backend_for_event_default(event):
    event.mail_settings["smtp_use_custom"] = ""
    backend = mail_backend_for_event(event)
    assert not isinstance(backend, CustomSMTPBackend)


def test_mail_backend_for_event_custom(event):
    event.mail_settings["smtp_use_custom"] = True
    event.mail_settings["smtp_host"] = "mail.example.com"
    event.mail_settings["smtp_port"] = 465
    event.mail_settings["smtp_username"] = "user"
    event.mail_settings["smtp_password"] = "pass"
    event.mail_settings["smtp_use_tls"] = False
    event.mail_settings["smtp_use_ssl"] = True

    backend = mail_backend_for_event(event)

    assert isinstance(backend, CustomSMTPBackend)


def test_mail_backend_for_event_force_custom(event):
    event.mail_settings["smtp_use_custom"] = ""
    event.mail_settings["smtp_host"] = "mail.example.com"

    backend = mail_backend_for_event(event, force_custom=True)

    assert isinstance(backend, CustomSMTPBackend)


@pytest.mark.parametrize(("force_custom", "timeout"), ((True, 10), (False, None)))
def test_mail_backend_for_event_socket_timeout(event, force_custom, timeout):
    event.mail_settings["smtp_use_custom"] = True
    event.mail_settings["smtp_host"] = "smtp.example.com"
    res = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 587))]

    with (
        patch("socket.socket") as mock_socket,
        patch("socket.getaddrinfo", return_value=res),
        patch("smtplib.SMTP.getreply", return_value=(220, b"")),
    ):
        mail_backend_for_event(event, force_custom=force_custom).open()

    if timeout is None:
        mock_socket.return_value.settimeout.assert_not_called()
    else:
        mock_socket.return_value.settimeout.assert_called_once_with(timeout)


def test_deliver_persisted_without_reachable_recipients_raises(event):
    with scopes_disabled():
        managed = SpeakerFactory(event=event, user=None, email=None, name="No Mail")
    mail = QueuedMailFactory(event=event, to=None)
    mail.to_speakers.add(managed)

    with scopes_disabled(), pytest.raises(SendMailException):
        deliver_persisted(mail)
