# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.core import mail as djmail
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretalx.mail.domain.queue import (
    bulk_create_drafts,
    copy_to_draft,
    expire_stale_queued_mails,
    send_outbox_mails,
)
from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.models import QueuedMail
from tests.factories import (
    EventFactory,
    MailTemplateFactory,
    QueuedMailFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    UserFactory,
)

pytestmark = [pytest.mark.django_db]


def test_send_outbox_mails_sends_draft_mails():
    event = EventFactory()
    user = UserFactory()
    mail_a = QueuedMailFactory(event=event, to=user.email)
    mail_b = QueuedMailFactory(event=event, to=user.email)
    djmail.outbox = []

    with scope(event=event):
        result = send_outbox_mails(event=event, mail_pks=[mail_a.pk, mail_b.pk])

    assert result == {"count": 2}
    assert len(djmail.outbox) == 2


def test_send_outbox_mails_skips_non_draft():
    """Mails that are no longer DRAFT (e.g. already sent) are skipped."""
    event = EventFactory()
    user = UserFactory()
    draft_mail = QueuedMailFactory(event=event, to=user.email)
    sent_mail = QueuedMailFactory(
        event=event, to=user.email, state=QueuedMailStates.SENT
    )
    djmail.outbox = []

    with scope(event=event):
        result = send_outbox_mails(event=event, mail_pks=[draft_mail.pk, sent_mail.pk])

    assert result == {"count": 1}
    assert len(djmail.outbox) == 1


def test_send_outbox_mails_with_requestor():
    event = EventFactory()
    user = UserFactory()
    requestor = UserFactory()
    mail = QueuedMailFactory(event=event, to=user.email)
    djmail.outbox = []

    with scope(event=event):
        result = send_outbox_mails(event=event, mail_pks=[mail.pk], requestor=requestor)

    assert result == {"count": 1}
    assert len(djmail.outbox) == 1


def test_send_outbox_mails_empty_list():
    event = EventFactory()

    with scope(event=event):
        result = send_outbox_mails(event=event, mail_pks=[])

    assert result == {"count": 0}


def test_send_outbox_mails_handles_send_failure(monkeypatch):
    event = EventFactory()
    user = UserFactory()
    mail = QueuedMailFactory(event=event, to=user.email)

    def broken_send(*args, **kwargs):
        raise RuntimeError("SMTP exploded")

    monkeypatch.setattr("pretalx.mail.domain.queue.send_draft", broken_send)

    with scope(event=event):
        result = send_outbox_mails(event=event, mail_pks=[mail.pk])

    assert result == {"count": 1}


def test_stale_sending_mail_marked_as_failed(event):
    """Mails stuck in SENDING state for over an hour are marked as failed
    with a timeout error."""
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)
    with scopes_disabled():
        QueuedMail.objects.filter(pk=mail.pk).update(
            updated=now() - dt.timedelta(hours=2)
        )

    count = expire_stale_queued_mails()

    assert count == 1
    with scopes_disabled():
        mail.refresh_from_db()
    assert mail.state == QueuedMailStates.DRAFT
    assert mail.has_error is True
    assert "Timed out" in mail.error_data["error"]
    assert mail.error_data["type"] == "TimeoutError"


def test_recent_sending_mail_not_marked_as_failed(event):
    mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)

    count = expire_stale_queued_mails()

    assert count == 0
    with scopes_disabled():
        mail.refresh_from_db()
    assert mail.state == QueuedMailStates.SENDING
    assert mail.has_error is False


def test_copy_to_draft_creates_new_draft(event):
    original = QueuedMailFactory(
        event=event,
        state=QueuedMailStates.SENT,
        subject="Original",
        text="Original text",
        to="recipient@example.com",
        error_data={"error": "stale"},
    )

    with scope(event=event):
        copy = copy_to_draft(original)

    assert copy.pk != original.pk
    assert copy.state == QueuedMailStates.DRAFT
    assert copy.sent is None
    assert copy.error_data is None
    assert copy.error_timestamp is None
    assert copy.subject == "Original"
    assert copy.text == "Original text"
    assert copy.to == "recipient@example.com"


def test_copy_to_draft_preserves_to_users(event):
    user = UserFactory()
    original = QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
    original.to_users.add(user)

    with scope(event=event):
        copy = copy_to_draft(original)
        assert list(copy.to_users.all()) == [user]


def test_bulk_create_drafts_skips_missing_user(event):
    template = MailTemplateFactory(event=event)
    with scope(event=event):
        mails, render_failures = bulk_create_drafts(template, [{"user_id": 999999}])
        assert mails == []
        assert render_failures == 0
        assert event.queued_mails.count() == 0


def test_bulk_create_drafts_persists_one_per_unique_recipient(event):
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    user = UserFactory()
    with scope(event=event):
        mails, render_failures = bulk_create_drafts(template, [{"user_id": user.pk}])
    assert render_failures == 0
    assert len(mails) == 1
    mail = mails[0]
    assert mail.pk is not None
    assert mail.state == QueuedMailStates.DRAFT
    assert mail.subject == "Hi"
    assert mail.text == "Body"
    with scope(event=event):
        assert list(mail.to_users.all()) == [user]
        assert list(mail.submissions.all()) == []


def test_bulk_create_drafts_dedups_identical_subject_and_text(event):
    """Two recipients with the same user, subject and text collapse into a
    single saved draft with both submissions attached."""
    template = MailTemplateFactory(event=event, subject="Hi", text="Same body")
    speaker = SpeakerFactory(event=event)
    sub_a = SubmissionFactory(event=event)
    sub_b = SubmissionFactory(event=event)
    with scope(event=event):
        sub_a.speakers.add(speaker)
        sub_b.speakers.add(speaker)
        mails, render_failures = bulk_create_drafts(
            template,
            [
                {"user_id": speaker.user.pk, "submission_id": sub_a.pk},
                {"user_id": speaker.user.pk, "submission_id": sub_b.pk},
            ],
        )
    assert render_failures == 0
    assert len(mails) == 1
    mail = mails[0]
    with scope(event=event):
        assert list(mail.to_users.all()) == [speaker.user]
        assert {s.pk for s in mail.submissions.all()} == {sub_a.pk, sub_b.pk}


def test_bulk_create_drafts_resolves_slot_for_recipient(event):
    """A ``slot_id`` on a recipient row is loaded and made available in
    the template context — placeholders like ``{session_room}`` resolve."""
    submission = SubmissionFactory(event=event)
    user = UserFactory()
    template = MailTemplateFactory(
        event=event, subject="Hi", text="Body in {session_room}"
    )
    with scope(event=event):
        slot = TalkSlotFactory(submission=submission)
        mails, render_failures = bulk_create_drafts(
            template,
            [{"user_id": user.pk, "submission_id": submission.pk, "slot_id": slot.pk}],
        )
    assert render_failures == 0
    assert len(mails) == 1
    assert str(slot.room.name) in mails[0].text


def test_bulk_create_drafts_counts_render_failures(event):
    """When a template render raises SendMailException, the recipient is
    skipped and the failure is counted; nothing is persisted."""
    template = MailTemplateFactory(
        event=event, subject="Hi {nonexistent_placeholder}", text="Body"
    )
    user = UserFactory()
    with scope(event=event):
        mails, render_failures = bulk_create_drafts(template, [{"user_id": user.pk}])
        assert mails == []
        assert render_failures == 1
        assert event.queued_mails.count() == 0


def test_bulk_create_drafts_progress_callback_fires_per_recipient(event):
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    user = UserFactory()
    progress_calls = []
    with scope(event=event):
        bulk_create_drafts(
            template,
            [{"user_id": user.pk}, {"user_id": 999999}],
            progress=lambda current, total: progress_calls.append((current, total)),
        )
    assert progress_calls == [(1, 2), (2, 2)]
