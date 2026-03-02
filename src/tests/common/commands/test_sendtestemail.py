# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from unittest.mock import patch

import pytest
from django.core import mail as djmail
from django.core.management import call_command

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_sendtestemail_sends_email(settings):
    djmail.outbox = []

    call_command("sendtestemail", "test@example.com")

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["test@example.com"]
    assert djmail.outbox[0].from_email == f"pretalx <{settings.MAIL_FROM}>"
    assert djmail.outbox[0].subject == "pretalx test email"
    assert djmail.outbox[0].body == (
        "This is a test email from pretalx to verify your email configuration is working correctly."
    )


def test_sendtestemail_sends_to_multiple_addresses():
    djmail.outbox = []

    call_command("sendtestemail", "a@example.com", "b@example.com")

    assert len(djmail.outbox) == 2
    assert djmail.outbox[0].to == ["a@example.com"]
    assert djmail.outbox[1].to == ["b@example.com"]


def test_sendtestemail_handles_smtp_error_gracefully():
    djmail.outbox = []

    # Mocking mail_send_task.apply: need to simulate SMTP failure,
    # which is impossible with the locmem backend (system boundary).
    with patch(
        "pretalx.common.mail.mail_send_task.apply",
        side_effect=OSError("Connection refused"),
    ):
        call_command("sendtestemail", "test@example.com")

    assert djmail.outbox == []
