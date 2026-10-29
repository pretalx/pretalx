# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import smtplib

import pytest
from django_scopes import scope, scopes_disabled

from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.models import QueuedMail
from tests.factories import MailTemplateFactory, QueuedMailFactory, SpeakerFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_mail_template_log_parent_is_event(event):
    template = MailTemplateFactory(event=event)
    assert template.log_parent == event


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


@pytest.mark.parametrize(
    ("exception", "expected_error_data"),
    (
        (
            ConnectionError("Connection refused"),
            {"error": "Connection refused", "type": "ConnectionError"},
        ),
        (
            smtplib.SMTPResponseException(550, b"Mailbox not found"),
            {
                "error": "Mailbox not found",
                "type": "SMTPResponseException",
                "smtp_code": 550,
            },
        ),
        (
            smtplib.SMTPResponseException(451, b"Temporary failure"),
            {
                "error": "Temporary failure",
                "type": "SMTPResponseException",
                "smtp_code": 451,
            },
        ),
        (
            smtplib.SMTPResponseException(550, "Already a string"),
            {
                "error": "Already a string",
                "type": "SMTPResponseException",
                "smtp_code": 550,
            },
        ),
    ),
    ids=("connection_error", "smtp_bytes", "smtp_temporary", "smtp_str"),
)
def test_queued_mail_mark_failed_stores_error(exception, expected_error_data):
    mail = QueuedMailFactory(state=QueuedMailStates.SENDING)

    mail.mark_failed(exception)
    mail.refresh_from_db()

    assert mail.state == QueuedMailStates.DRAFT
    assert mail.error_data == expected_error_data
    assert mail.error_timestamp is not None


def test_queued_mail_prefixed_subject_without_event():
    mail = QueuedMail(subject="Hello", text="Body")
    assert mail.prefixed_subject == "Hello"


def test_queued_mail_prefixed_subject_with_event_prefix(event):
    event.mail_settings["subject_prefix"] = "TestConf"
    mail = QueuedMailFactory(event=event, subject="Hello")
    assert mail.prefixed_subject == "[TestConf] Hello"


def test_queued_mail_prefetch_recipients_avoids_extra_queries(
    event, django_assert_num_queries
):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
    mail = QueuedMailFactory(event=event)
    mail.to_speakers.add(speaker)

    with scope(event=event):
        mails = list(QueuedMail.objects.prefetch_recipients(event))

    with django_assert_num_queries(0):
        speakers = list(mails[0].to_speakers.all())
    assert speakers == [speaker]


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
