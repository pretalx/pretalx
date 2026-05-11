# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.mail.domain.smtp import mail_backend_for_event
from pretalx.mail.smtp import CustomSMTPBackend

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_mail_backend_for_event_default(event):
    """Returns the default Django mail backend when smtp_use_custom is falsy."""
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
