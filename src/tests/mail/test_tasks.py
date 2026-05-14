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
from pretalx.mail.receivers import expire_stale_mails_periodic
from pretalx.mail.tasks import (
    mail_send_task,
    task_create_mails_for_template,
    task_send_draft,
    task_send_outbox_mails,
    task_send_transient,
)
from tests.factories import (
    EventFactory,
    MailTemplateFactory,
    QueuedMailFactory,
    UserFactory,
)

pytestmark = [pytest.mark.django_db]


# Module path used by tests that monkeypatch `get_connection`. Importing
# from `pretalx.mail.domain.smtp` puts the symbol in that module's namespace,
# so that's where we patch it.
GET_CONNECTION_PATH = "pretalx.mail.domain.smtp.get_connection"


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
    """The receivers.py receiver delegates to the domain helper and emits a
    warning when anything was reset."""
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)
    with scopes_disabled():
        QueuedMail.objects.filter(pk=mail.pk).update(
            updated=now() - dt.timedelta(hours=2)
        )

    with caplog.at_level("WARNING", logger="pretalx.mail.receivers"):
        expire_stale_mails_periodic(sender=None)

    with scopes_disabled():
        mail.refresh_from_db()
    assert mail.state == QueuedMailStates.DRAFT
    assert "Expired 1 stale queued mails" in caplog.text


# ---------------------------------------------------------------------------
# task_send_draft
# ---------------------------------------------------------------------------


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_send_draft_renders_and_marks_sent(event):
    mail = QueuedMailFactory(
        event=event, state=QueuedMailStates.SENDING, to="recipient@test.org"
    )
    djmail.outbox = []

    task_send_draft(mail.pk)

    mail.refresh_from_db()
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["recipient@test.org"]
    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None


def test_send_draft_missing_id_logs_warning(caplog):
    with caplog.at_level("WARNING", logger="pretalx.mail.tasks"):
        task_send_draft(999999)
    assert "QueuedMail 999999 not found" in caplog.text


@pytest.mark.parametrize(
    ("exception", "expected_error_type"),
    (
        (SMTPResponseException(500, b"Error"), "SMTPResponseException"),
        (ConnectionError("Connection refused"), "ConnectionError"),
    ),
)
def test_send_draft_send_error_marks_failed(event, exception, expected_error_type):
    mail = QueuedMailFactory(
        event=event, state=QueuedMailStates.SENDING, to="recipient@test.org"
    )

    # Mocking get_mail_backend: need to simulate SMTP failure (system boundary).
    mock_backend = MagicMock()
    mock_backend.send_messages.side_effect = exception

    with patch(
        "pretalx.mail.domain.smtp.mail_backend_for_event", return_value=mock_backend
    ):
        task_send_draft(mail.pk)

    mail.refresh_from_db()
    assert mail.state == QueuedMailStates.DRAFT
    assert mail.error_data["type"] == expected_error_type


def test_send_draft_retryable_smtp_error_marks_failed_after_max_retries(event):
    mail = QueuedMailFactory(
        event=event, state=QueuedMailStates.SENDING, to="recipient@test.org"
    )

    # Mocking get_mail_backend: need to simulate SMTP failure (system boundary).
    mock_backend = MagicMock()
    mock_backend.send_messages.side_effect = SMTPResponseException(
        421, b"Service not available"
    )

    with (
        patch(
            "pretalx.mail.domain.smtp.mail_backend_for_event", return_value=mock_backend
        ),
        # Mocking retry: simulate exhausted retries directly to test the
        # error handling path without 5 recursive calls.
        patch.object(
            task_send_draft,
            "retry",
            side_effect=task_send_draft.MaxRetriesExceededError(),
        ),
    ):
        task_send_draft(mail.pk)

    mail.refresh_from_db()
    assert mail.state == QueuedMailStates.DRAFT
    assert mail.error_data["type"] == "SMTPResponseException"


def test_send_draft_retryable_smtp_error_reschedules(event):
    """A retryable SMTP error must propagate ``celery.exceptions.Retry`` so
    the worker reschedules the task. The row is left in SENDING (not marked
    failed) and ``task.retry`` is invoked with an exponential countdown."""
    from celery.exceptions import Retry  # noqa: PLC0415

    mail = QueuedMailFactory(
        event=event, state=QueuedMailStates.SENDING, to="recipient@test.org"
    )
    mock_backend = MagicMock()
    mock_backend.send_messages.side_effect = SMTPResponseException(
        421, b"Service not available"
    )

    with (
        patch(
            "pretalx.mail.domain.smtp.mail_backend_for_event", return_value=mock_backend
        ),
        patch.object(task_send_draft, "retry", side_effect=Retry()) as retry_mock,
        pytest.raises(Retry),
    ):
        task_send_draft(mail.pk)

    retry_mock.assert_called_once()
    assert retry_mock.call_args.kwargs["max_retries"] == 5
    mail.refresh_from_db()
    assert mail.state == QueuedMailStates.SENDING
    assert mail.error_data is None


def test_send_draft_no_recipients_marks_sent(event):
    """When the row has no deliverable addresses (e.g. every recipient was
    stripped by the debug-domain filter in production), the task records
    the mail as sent rather than leaving it stuck in SENDING — the row
    has been processed, there is just nothing on the wire."""
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING, to=None)
    djmail.outbox = []

    task_send_draft(mail.pk)

    mail.refresh_from_db()
    assert djmail.outbox == []
    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None


def test_send_draft_render_failure_marks_failed(event):
    """Errors raised while rendering the message (template, CSS inlining,
    etc.) are terminal failures: the row is marked DRAFT with error
    data, not silently abandoned in SENDING."""
    mail = QueuedMailFactory(
        event=event, state=QueuedMailStates.SENDING, to="recipient@test.org"
    )

    with patch(
        "pretalx.mail.domain.smtp.build_message",
        side_effect=RuntimeError("render boom"),
    ) as build_mock:
        task_send_draft(mail.pk)
    build_mock.assert_called_once()

    mail.refresh_from_db()
    assert mail.state == QueuedMailStates.DRAFT
    assert mail.error_data["type"] == "RuntimeError"
    assert "render boom" in mail.error_data["error"]


# ---------------------------------------------------------------------------
# task_send_transient
# ---------------------------------------------------------------------------


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    MAIL_FROM="orga@orga.org",
)
def test_send_transient_sends():
    djmail.outbox = []

    task_send_transient(
        to="recipient@test.org", subject="Subject", body="Body", html=None
    )

    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["recipient@test.org"]
    assert djmail.outbox[0].subject == "Subject"


def test_send_transient_empty_recipients_is_noop():
    djmail.outbox = []

    task_send_transient(to=[], subject="S", body="B", html=None)

    assert djmail.outbox == []


@pytest.mark.parametrize(
    "exception",
    (SMTPResponseException(500, b"Error"), ConnectionError("Connection refused")),
)
@override_settings(MAIL_FROM="orga@orga.org")
def test_send_transient_send_error_raises(exception):
    # Mocking get_connection: need to simulate send failure, which is
    # impossible with the locmem backend (system boundary).
    mock_backend = MagicMock()
    mock_backend.send_messages.side_effect = exception

    with (
        patch(GET_CONNECTION_PATH, return_value=mock_backend),
        pytest.raises(SendMailException),
    ):
        task_send_transient(to="recipient@test.org", subject="S", body="B", html=None)


@override_settings(MAIL_FROM="orga@orga.org")
def test_send_transient_retryable_smtp_error_raises_send_mail_exception_after_retries():
    """Retry exhaustion on a transient mail surfaces as
    :class:`SendMailException` so celery logs it as a hard failure;
    there is no row to mark."""
    mock_backend = MagicMock()
    mock_backend.send_messages.side_effect = SMTPResponseException(
        421, b"Service not available"
    )

    with (
        patch(GET_CONNECTION_PATH, return_value=mock_backend),
        # Mocking retry: simulate exhausted retries directly (avoids 5
        # recursive task invocations in test mode).
        patch.object(
            task_send_transient,
            "retry",
            side_effect=task_send_transient.MaxRetriesExceededError(),
        ),
        pytest.raises(SendMailException),
    ):
        task_send_transient(to="recipient@test.org", subject="S", body="B", html=None)


@override_settings(MAIL_FROM="orga@orga.org")
def test_send_transient_retryable_smtp_error_reschedules():
    """A retryable SMTP error must propagate ``Retry`` so Celery
    reschedules — it must not be wrapped in ``SendMailException`` (which
    would tell Celery the task failed terminally)."""
    from celery.exceptions import Retry  # noqa: PLC0415

    mock_backend = MagicMock()
    mock_backend.send_messages.side_effect = SMTPResponseException(
        421, b"Service not available"
    )

    with (
        patch(GET_CONNECTION_PATH, return_value=mock_backend),
        patch.object(task_send_transient, "retry", side_effect=Retry()) as retry_mock,
        pytest.raises(Retry),
    ):
        task_send_transient(to="recipient@test.org", subject="S", body="B", html=None)

    retry_mock.assert_called_once()


# ---------------------------------------------------------------------------
# mail_send_task (deprecated shim)
# ---------------------------------------------------------------------------


def test_mail_send_task_shim_with_queued_mail_id_routes_to_queued_dispatch():
    """In-flight jobs from the old task name carrying ``queued_mail_id``
    must reach :func:`task_send_draft` so the row state stays
    in sync; routing them through the transient task would leave the row
    stuck in SENDING."""
    with (
        patch.object(task_send_draft, "apply_async") as queued_mock,
        patch.object(task_send_transient, "apply_async") as transient_mock,
    ):
        mail_send_task(
            queued_mail_id=42, to=["x@y.org"], subject="S", body="B", html=None
        )

    queued_mock.assert_called_once_with(args=[42], ignore_result=True)
    transient_mock.assert_not_called()


def test_mail_send_task_shim_without_queued_mail_id_routes_to_transient_dispatch():
    """Transient in-flight jobs (no ``queued_mail_id``) re-queue under
    the new transient task; legacy ``event`` kwarg is renamed to
    ``event_id`` and ``headers`` is dropped."""
    with patch.object(task_send_transient, "apply_async") as mock:
        mail_send_task(
            to=["x@y.org"],
            subject="S",
            body="B",
            html=None,
            event=7,
            headers={"X-Old": "y"},
        )

    forwarded = mock.call_args.kwargs["kwargs"]
    assert forwarded["to"] == ["x@y.org"]
    assert forwarded["event_id"] == 7
    assert "event" not in forwarded
    assert "headers" not in forwarded


def test_mail_send_task_shim_without_event_kwarg_forwards_unchanged():
    """The legacy ``event`` rename only fires when the kwarg is present;
    eventless transient jobs pass straight through."""
    with patch.object(task_send_transient, "apply_async") as mock:
        mail_send_task(to=["x@y.org"], subject="S", body="B", html=None)

    forwarded = mock.call_args.kwargs["kwargs"]
    assert "event_id" not in forwarded
    assert "event" not in forwarded


# ---------------------------------------------------------------------------
# task_create_mails_for_template
# ---------------------------------------------------------------------------


def test_create_mails_for_template_skip_queue_dispatches_each_mail(event):
    """skip_queue=True hands every persisted mail to send_draft —
    the only signal that the row is being shipped immediately rather than
    left as a draft."""
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    user = UserFactory()
    task_data = {
        "template_id": template.pk,
        "recipients": [{"user_id": user.pk}],
        "skip_queue": True,
    }

    with patch("pretalx.mail.domain.send.send_draft") as dispatch_mock:
        result = task_create_mails_for_template.apply(kwargs=task_data).result

    assert result == {"count": 1, "render_failures": 0, "skip_queue": True}
    dispatch_mock.assert_called_once()


def test_create_mails_for_template_skip_queue_logs_dispatch_failures(event, caplog):
    """When send_draft raises during skip_queue delivery, the task
    swallows the exception, logs it, and still reports the mail as
    successfully created — the row is persisted even if dispatch failed."""
    template = MailTemplateFactory(event=event, subject="Boom", text="Body")
    user = UserFactory()
    task_data = {
        "template_id": template.pk,
        "recipients": [{"user_id": user.pk}],
        "skip_queue": True,
    }

    with (
        patch(
            "pretalx.mail.domain.send.send_draft",
            side_effect=RuntimeError("SMTP exploded"),
        ),
        caplog.at_level("ERROR", logger="pretalx.mail.tasks"),
    ):
        result = task_create_mails_for_template.apply(kwargs=task_data).result

    assert result == {"count": 1, "render_failures": 0, "skip_queue": True}
    assert "Failed to send mail" in caplog.text
    with scopes_disabled():
        assert QueuedMail.objects.filter(template_id=template.pk).count() == 1
