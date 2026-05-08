# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.core import mail as djmail
from django.core.exceptions import ValidationError
from django.utils.timezone import now as tz_now

from pretalx.common import mail as common_mail
from pretalx.mail.domain.send import send_queued_mail
from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.models import QueuedMail
from pretalx.mail.signals import queuedmail_pre_send
from tests.factories import QueuedMailFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize("state", (QueuedMailStates.SENT, QueuedMailStates.SENDING))
def test_send_non_draft_raises(event, state):
    mail = QueuedMailFactory(event=event, state=state, to="a@b.com")
    with pytest.raises(ValidationError):
        mail.send()


def test_send_delivers_email(event):
    """Sending a persisted draft mail dispatches it via the celery task,
    which delivers the email and marks the mail as sent."""
    djmail.outbox = []
    user = UserFactory()
    mail = QueuedMailFactory(event=event, to="test@pretalx.org")
    mail.to_users.add(user)

    mail.send()
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None
    assert len(djmail.outbox) == 1
    sent_email = djmail.outbox[0]
    assert set(sent_email.to) == {"test@pretalx.org", user.email}
    assert sent_email.subject == mail.prefixed_subject
    assert mail.text in sent_email.body


def test_send_non_persisted_delivers_email(event):
    """A non-persisted mail (created with commit=False) goes through the
    fire-and-forget path, setting sent and state in-memory."""
    djmail.outbox = []
    mail = QueuedMail(
        event=event, to="test@pretalx.org", subject="Test", text="Body", locale="en"
    )

    mail.send()

    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None
    assert len(djmail.outbox) == 1


def test_send_without_event_delivers_email():
    """A persisted mail without an event skips the pre_send signal but
    still dispatches the celery task."""
    djmail.outbox = []
    mail = QueuedMailFactory(event=None, to="test@pretalx.org")

    mail.send()
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert len(djmail.outbox) == 1


def test_send_skips_dispatch_when_signal_sets_sent(event, register_signal_handler):
    """When a pre_send signal handler sets mail.sent, send() returns early
    without dispatching the celery task again."""

    def mark_as_sent(signal, sender, mail, **kwargs):
        mail.sent = tz_now()

    register_signal_handler(queuedmail_pre_send, mark_as_sent)
    djmail.outbox = []
    mail = QueuedMailFactory(event=event, to="test@pretalx.org")

    mail.send()
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None
    assert len(djmail.outbox) == 0


def test_send_broker_failure_marks_failed(event, monkeypatch):
    """When the celery broker is unreachable (OSError), the mail is marked
    as failed rather than crashing."""

    def broken_broker(**kwargs):
        raise OSError("Broker unavailable")

    monkeypatch.setattr(common_mail.mail_send_task, "apply_async", broken_broker)
    mail = QueuedMailFactory(event=event, to="test@pretalx.org")

    mail.send()
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.DRAFT
    assert mail.has_error is True
    assert "Broker unavailable" in mail.error_data["error"]


def test_send_after_failure_clears_error(event):
    """When a previously failed mail is sent again, the error data and
    timestamp are cleared on successful dispatch."""
    djmail.outbox = []
    mail = QueuedMailFactory(
        event=event,
        to="test@pretalx.org",
        error_data={"error": "previous failure"},
        error_timestamp="2024-01-01T00:00:00Z",
    )
    assert mail.has_error is True

    mail.send()
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert mail.error_data is None
    assert mail.error_timestamp is None


def test_send_with_comma_separated_to(event):
    """When the 'to' field contains comma-separated addresses, all of them
    receive the email."""
    djmail.outbox = []
    mail = QueuedMailFactory(event=event, to="a@example.com,b@example.com")

    mail.send()
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert len(djmail.outbox) == 1
    assert set(djmail.outbox[0].to) == {"a@example.com", "b@example.com"}


def test_send_queued_mail_callable_directly(event):
    """The domain function works without going through the model thin
    method."""
    djmail.outbox = []
    mail = QueuedMailFactory(event=event, to="test@pretalx.org")

    send_queued_mail(mail)
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert len(djmail.outbox) == 1
