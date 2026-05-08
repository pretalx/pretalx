# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import smtplib

import pytest
from django_scopes import scope

from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.models import QueuedMail
from tests.factories import MailTemplateFactory, QueuedMailFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_mail_template_str_contains_event_and_subject(event):
    template = MailTemplateFactory(event=event, subject="Welcome!")
    result = str(template)
    assert event.slug in result
    assert "Welcome!" in result


def test_mail_template_log_parent_is_event(event):
    template = MailTemplateFactory(event=event)
    assert template.log_parent == event


def test_queued_mail_str_contains_to_subject_state():
    mail = QueuedMailFactory(to="test@example.com", subject="Hello")
    result = str(mail)
    assert "test@example.com" in result
    assert "Hello" in result
    assert "draft" in result


@pytest.mark.parametrize(
    ("state", "error_data", "expected"),
    (
        (QueuedMailStates.DRAFT, {"error": "Connection refused"}, True),
        (QueuedMailStates.DRAFT, None, False),
        (QueuedMailStates.SENT, {"error": "stale"}, False),
    ),
)
def test_queued_mail_has_error_requires_draft_and_error_data(
    state, error_data, expected
):
    mail = QueuedMailFactory(state=state, error_data=error_data)
    assert mail.has_error is expected


def test_queued_mail_mark_sent_updates_state_and_timestamp():
    mail = QueuedMailFactory(
        state=QueuedMailStates.SENDING,
        error_data={"error": "previous"},
        error_timestamp="2024-01-01T00:00:00Z",
    )

    mail.mark_sent()
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.SENT
    assert mail.sent is not None
    assert mail.error_data is None
    assert mail.error_timestamp is None


def test_queued_mail_mark_failed_stores_error():
    mail = QueuedMailFactory(state=QueuedMailStates.SENDING)

    mail.mark_failed(ConnectionError("Connection refused"))
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.DRAFT
    assert mail.error_data["type"] == "ConnectionError"
    assert "Connection refused" in mail.error_data["error"]
    assert mail.error_timestamp is not None


@pytest.mark.parametrize(
    ("smtp_code", "smtp_error", "expected_error_str"),
    (
        (550, b"Mailbox not found", "Mailbox not found"),
        (451, b"Temporary failure", "Temporary failure"),
        (550, "Already a string", "Already a string"),
    ),
)
def test_queued_mail_mark_failed_with_smtp_exception(
    smtp_code, smtp_error, expected_error_str
):
    """SMTPResponseException errors store the SMTP status code and
    decode byte error messages to UTF-8."""
    mail = QueuedMailFactory(state=QueuedMailStates.SENDING)
    exc = smtplib.SMTPResponseException(smtp_code, smtp_error)

    mail.mark_failed(exc)
    mail.refresh_from_db()

    assert mail.error_data["smtp_code"] == smtp_code
    assert mail.error_data["error"] == expected_error_str


def test_queued_mail_prefixed_subject_without_event():
    mail = QueuedMail(subject="Hello", text="Body")
    assert mail.prefixed_subject == "Hello"


def test_queued_mail_prefixed_subject_with_event_prefix(event):
    event.mail_settings["subject_prefix"] = "TestConf"
    mail = QueuedMailFactory(event=event, subject="Hello")
    assert mail.prefixed_subject == "[TestConf] Hello"


def test_queued_mail_prefetch_users_avoids_extra_queries(
    event, django_assert_num_queries
):
    """prefetch_users eagerly loads to_users so accessing them needs no
    additional queries."""
    user = UserFactory()
    mail = QueuedMailFactory(event=event)
    mail.to_users.add(user)

    with scope(event=event):
        mails = list(QueuedMail.objects.prefetch_users(event))

    # Accessing to_users should not trigger any queries thanks to prefetching
    with django_assert_num_queries(0):
        users = list(mails[0].to_users.all())
    assert users == [user]


@pytest.mark.parametrize(
    ("state", "error_data", "expected_computed_state"),
    (
        (QueuedMailStates.DRAFT, {"error": "oops"}, "failed"),
        (QueuedMailStates.DRAFT, None, "draft"),
        (QueuedMailStates.SENT, None, "sent"),
        (QueuedMailStates.SENDING, None, "sending"),
    ),
)
def test_queued_mail_with_computed_state_annotates_correctly(
    event, state, error_data, expected_computed_state
):
    mail = QueuedMailFactory(event=event, state=state, error_data=error_data)
    with scope(event=event):
        result = QueuedMail.objects.with_computed_state().get(pk=mail.pk)
    assert result.computed_state == expected_computed_state
