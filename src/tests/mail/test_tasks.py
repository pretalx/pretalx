# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Raphael Michel
import datetime as dt
from smtplib import SMTPResponseException
from unittest.mock import MagicMock, patch

import pytest
from django.core import mail as djmail
from django.test import override_settings
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.common.exceptions import SendMailException
from pretalx.common.models.log import ActivityLog
from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.models import QueuedMail
from pretalx.mail.signals import expire_stale_mails_periodic
from pretalx.mail.tasks import (
    _mark_queued_mail_failed,
    _mark_queued_mail_sent,
    mail_send_task,
    task_send_outbox_mails,
)
from tests.factories import EventFactory, QueuedMailFactory, UserFactory

pytestmark = [pytest.mark.django_db]


# Module path used by tests that monkeypatch `get_connection`. Importing
# from `pretalx.mail.domain.send` puts the symbol in that module's namespace,
# so that's where we patch it.
GET_CONNECTION_PATH = "pretalx.mail.domain.send.get_connection"


def test_task_send_outbox_mails_dispatches_with_requestor():
    """The celery wrapper looks up the requestor by id and threads it through
    to mail.send so it lands on the activity log."""
    event = EventFactory()
    user = UserFactory()
    requestor = UserFactory()
    mail = QueuedMailFactory(event=event, to=user.email)
    djmail.outbox = []

    result = task_send_outbox_mails.apply(
        kwargs={
            "event_id": event.pk,
            "mail_pks": [mail.pk],
            "requestor_id": requestor.pk,
        }
    ).result

    assert result == {"count": 1}
    assert len(djmail.outbox) == 1
    with scopes_disabled():
        log = ActivityLog.objects.get(
            action_type="pretalx.mail.sent", object_id=mail.pk
        )
    assert log.person == requestor


def test_expire_stale_queued_mails_receiver_marks_and_logs(event, caplog):
    """The signals.py receiver delegates to the domain helper and emits a
    warning when anything was reset."""
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)
    with scopes_disabled():
        QueuedMail.objects.filter(pk=mail.pk).update(
            updated=now() - dt.timedelta(hours=2)
        )

    with caplog.at_level("WARNING", logger="pretalx.mail.signals"):
        expire_stale_mails_periodic(sender=None)

    with scopes_disabled():
        mail.refresh_from_db()
    assert mail.state == QueuedMailStates.DRAFT
    assert "Expired 1 stale queued mails" in caplog.text


def test_mark_queued_mail_sent_updates_state(event):
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)

    _mark_queued_mail_sent(mail.pk)
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None


def test_mark_queued_mail_sent_nonexistent_does_not_raise(caplog):
    with caplog.at_level("WARNING", logger="pretalx.mail.tasks"):
        _mark_queued_mail_sent(999999)
    assert "QueuedMail 999999 not found" in caplog.text


def test_mark_queued_mail_failed_updates_state_and_records_error(event):
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)

    _mark_queued_mail_failed(mail.pk, RuntimeError("Connection refused"))
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.DRAFT
    assert mail.error_data == {"error": "Connection refused", "type": "RuntimeError"}


def test_mark_queued_mail_failed_nonexistent_does_not_raise(caplog):
    with caplog.at_level("WARNING", logger="pretalx.mail.tasks"):
        _mark_queued_mail_failed(999999, RuntimeError("test"))
    assert "QueuedMail 999999 not found" in caplog.text


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_mail_send_task_marks_queued_mail_sent_on_success(event):
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)
    djmail.outbox = []

    mail_send_task(
        "recipient@test.org", "S", "B", None, event=event.pk, queued_mail_id=mail.pk
    )
    mail.refresh_from_db()

    assert len(djmail.outbox) == 1
    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None


@pytest.mark.parametrize(
    "exception",
    (SMTPResponseException(500, b"Error"), ConnectionError("Connection refused")),
)
@override_settings(MAIL_FROM="orga@orga.org")
def test_mail_send_task_send_error_without_queued_mail_raises(exception):
    # Mocking get_connection: need to simulate send failure, which is
    # impossible with the locmem backend (system boundary).
    mock_backend = MagicMock()
    mock_backend.send_messages.side_effect = exception

    with (
        patch(GET_CONNECTION_PATH, return_value=mock_backend),
        pytest.raises(SendMailException),
    ):
        mail_send_task("recipient@test.org", "S", "B", None)


@pytest.mark.parametrize(
    ("exception", "expected_error_type"),
    (
        (SMTPResponseException(500, b"Error"), "SMTPResponseException"),
        (ConnectionError("Connection refused"), "ConnectionError"),
    ),
)
@override_settings(MAIL_FROM="orga@orga.org")
def test_mail_send_task_send_error_with_queued_mail_marks_failed(
    event, exception, expected_error_type
):
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)

    # Mocking get_connection: need to simulate send failure (system boundary).
    mock_backend = MagicMock()
    mock_backend.send_messages.side_effect = exception

    with patch(GET_CONNECTION_PATH, return_value=mock_backend):
        mail_send_task("recipient@test.org", "S", "B", None, queued_mail_id=mail.pk)

    mail.refresh_from_db()
    assert mail.state == QueuedMailStates.DRAFT
    assert mail.error_data["type"] == expected_error_type


@override_settings(MAIL_FROM="orga@orga.org")
def test_mail_send_task_retryable_smtp_error_without_queued_mail_raises():
    # Mocking get_connection: need to simulate SMTP failure (system boundary).
    mock_backend = MagicMock()
    mock_backend.send_messages.side_effect = SMTPResponseException(
        421, b"Service not available"
    )

    with (
        patch(GET_CONNECTION_PATH, return_value=mock_backend),
        # Mocking retry: in test mode, celery retry() raises Retry which
        # triggers recursive re-execution. We simulate exhausted retries
        # directly to test the error handling path without 5 recursive calls.
        patch.object(
            mail_send_task,
            "retry",
            side_effect=mail_send_task.MaxRetriesExceededError(),
        ),
        pytest.raises(mail_send_task.MaxRetriesExceededError),
    ):
        mail_send_task("recipient@test.org", "S", "B", None)


@override_settings(MAIL_FROM="orga@orga.org")
def test_mail_send_task_retryable_smtp_error_with_queued_mail_marks_failed(event):
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)

    # Mocking get_connection: need to simulate SMTP failure (system boundary).
    mock_backend = MagicMock()
    mock_backend.send_messages.side_effect = SMTPResponseException(
        421, b"Service not available"
    )

    with (
        patch(GET_CONNECTION_PATH, return_value=mock_backend),
        # Mocking retry: simulate exhausted retries directly (see comment
        # in test above).
        patch.object(
            mail_send_task,
            "retry",
            side_effect=mail_send_task.MaxRetriesExceededError(),
        ),
    ):
        mail_send_task("recipient@test.org", "S", "B", None, queued_mail_id=mail.pk)

    mail.refresh_from_db()
    assert mail.state == QueuedMailStates.DRAFT
    assert mail.error_data["type"] == "SMTPResponseException"
