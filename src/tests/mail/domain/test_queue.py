# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.core import mail as djmail
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretalx.common.models.log import ActivityLog
from pretalx.mail.domain.queue import (
    bulk_create_drafts,
    copy_to_draft,
    expire_stale_queued_mails,
    save_draft,
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


def test_send_outbox_mails_sends_selected_drafts_with_requestor():
    event = EventFactory()
    user = UserFactory()
    requestor = UserFactory()
    mail_a = QueuedMailFactory(event=event, to=user.email)
    mail_b = QueuedMailFactory(event=event, to=user.email)
    sent_mail = QueuedMailFactory(
        event=event, to=user.email, state=QueuedMailStates.SENT
    )
    djmail.outbox = []

    with scope(event=event):
        assert send_outbox_mails(event=event, mail_pks=[]) == {"count": 0}
        result = send_outbox_mails(
            event=event,
            mail_pks=[mail_a.pk, mail_b.pk, sent_mail.pk],
            requestor=requestor,
        )

    assert result == {"count": 2}
    assert len(djmail.outbox) == 2
    with scopes_disabled():
        logs = ActivityLog.objects.filter(action_type="pretalx.mail.sent")
        assert sorted(logs.values_list("object_id", "person_id")) == sorted(
            [(mail_a.pk, requestor.pk), (mail_b.pk, requestor.pk)]
        )


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


def test_expire_stale_queued_mails_fails_only_stale_sending_mails(event):
    stale = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)
    recent = QueuedMailFactory(event=event, state=QueuedMailStates.SENDING)
    with scopes_disabled():
        QueuedMail.objects.filter(pk=stale.pk).update(
            updated=now() - dt.timedelta(hours=2)
        )

    count = expire_stale_queued_mails()

    assert count == 1
    with scopes_disabled():
        stale.refresh_from_db()
        recent.refresh_from_db()
    assert stale.state == QueuedMailStates.DRAFT
    assert stale.has_error is True
    assert "Timed out" in stale.error_data["error"]
    assert stale.error_data["type"] == "TimeoutError"
    assert recent.state == QueuedMailStates.SENDING
    assert recent.has_error is False


def test_copy_to_draft_creates_new_draft_with_reachable_speakers(event):
    with scope(event=event):
        reachable = SpeakerFactory(event=event)
        managed = SpeakerFactory(event=event, user=None, email=None, name="No Mail")
        original = QueuedMailFactory(
            event=event,
            state=QueuedMailStates.SENT,
            subject="Original",
            text="Original text",
            to="recipient@example.com",
            error_data={"error": "stale"},
        )
        original.to_speakers.add(reachable, managed)

        copy = copy_to_draft(original)

        assert copy.pk != original.pk
        assert copy.state == QueuedMailStates.DRAFT
        assert copy.sent is None
        assert copy.error_data is None
        assert copy.error_timestamp is None
        assert copy.subject == "Original"
        assert copy.text == "Original text"
        assert copy.to == "recipient@example.com"
        assert list(copy.to_speakers.all()) == [reachable]
        assert (
            managed.logged_actions().filter(action_type="pretalx.mail.skipped").count()
            == 1
        )


def test_copy_to_draft_all_speakers_unreachable_returns_none(event):
    with scope(event=event):
        managed = SpeakerFactory(event=event, user=None, email=None, name="No Mail")
        original = QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
        original.to_speakers.add(managed)

        result = copy_to_draft(original)

        assert result is None
        assert event.queued_mails.count() == 1


def test_save_draft_excludes_unreachable_speakers(event):
    with scope(event=event):
        reachable = SpeakerFactory(event=event)
        managed = SpeakerFactory(event=event, user=None, email=None, name="No Mail")
        mail = QueuedMail(event=event, subject="Hi", text="Body")

        result = save_draft(mail, to_speakers=[reachable, managed])

        assert result is mail
        assert list(mail.to_speakers.all()) == [reachable]
        skip_logs = managed.logged_actions().filter(action_type="pretalx.mail.skipped")
        assert skip_logs.count() == 1
        assert skip_logs.first().json_data["subject"] == "Hi"


def test_save_draft_drops_mail_with_only_unreachable_recipients(event):
    with scope(event=event):
        managed = SpeakerFactory(event=event, user=None, email=None, name="No Mail")
        mail = QueuedMail(event=event, subject="Hi", text="Body")

        result = save_draft(mail, to_speakers=[managed])

        assert result is None
        assert event.queued_mails.count() == 0
        assert (
            managed.logged_actions().filter(action_type="pretalx.mail.skipped").count()
            == 1
        )


def test_bulk_create_drafts_persists_one_per_speaker_and_reports_progress(event):
    template = MailTemplateFactory(event=event, subject="Hi", text="Hi {name},")
    speaker = SpeakerFactory(event=event, name="Jane Doe")
    speaker.user.name = "j-doe"
    speaker.user.save()
    progress_calls = []

    with scope(event=event):
        mails, render_failures = bulk_create_drafts(
            template,
            [{"speaker_id": speaker.pk}, {"speaker_id": 999999}],
            progress=lambda current, total: progress_calls.append((current, total)),
        )

        assert render_failures == 0
        assert progress_calls == [(1, 2), (2, 2)]
        assert len(mails) == 1
        mail = mails[0]
        assert mail.pk is not None
        assert mail.state == QueuedMailStates.DRAFT
        assert mail.subject == "Hi"
        assert mail.text == "Hi Jane Doe,"
        assert list(mail.to_speakers.all()) == [speaker]
        assert list(mail.submissions.all()) == []
        assert event.queued_mails.count() == 1


def test_bulk_create_drafts_skips_unreachable_and_profileless_recipients(event):
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    user = UserFactory()
    with scope(event=event):
        managed = SpeakerFactory(event=event, user=None, email=None, name="No Mail")

        mails, render_failures = bulk_create_drafts(
            template, [{"user_id": user.pk}, {"speaker_id": managed.pk}]
        )

        assert mails == []
        assert render_failures == 0
        assert event.queued_mails.count() == 0


def test_bulk_create_drafts_resolves_legacy_user_id_payload(event):
    # In-flight task payloads queued before the speaker_id rekeying
    # deployed still arrive keyed by user_id.
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    speaker = SpeakerFactory(event=event)
    with scope(event=event):
        mails, render_failures = bulk_create_drafts(
            template, [{"user_id": speaker.user.pk}]
        )
    assert render_failures == 0
    assert len(mails) == 1
    with scope(event=event):
        assert list(mails[0].to_speakers.all()) == [speaker]


def test_bulk_create_drafts_dedups_identical_subject_and_text(event):
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
                {"speaker_id": speaker.pk, "submission_id": sub_a.pk},
                {"speaker_id": speaker.pk, "submission_id": sub_b.pk},
            ],
        )
    assert render_failures == 0
    assert len(mails) == 1
    mail = mails[0]
    with scope(event=event):
        assert list(mail.to_speakers.all()) == [speaker]
        assert {s.pk for s in mail.submissions.all()} == {sub_a.pk, sub_b.pk}


def test_bulk_create_drafts_resolves_slot_for_recipient(event):
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    template = MailTemplateFactory(
        event=event, subject="Hi", text="Body in {session_room}"
    )
    with scope(event=event):
        slot = TalkSlotFactory(submission=submission)
        mails, render_failures = bulk_create_drafts(
            template,
            [
                {
                    "speaker_id": speaker.pk,
                    "submission_id": submission.pk,
                    "slot_id": slot.pk,
                }
            ],
        )
    assert render_failures == 0
    assert len(mails) == 1
    assert mails[0].text == f"Body in {slot.room.name}"


def test_bulk_create_drafts_counts_render_failures(event):
    template = MailTemplateFactory(
        event=event, subject="Hi {nonexistent_placeholder}", text="Body"
    )
    speaker = SpeakerFactory(event=event)
    with scope(event=event):
        mails, render_failures = bulk_create_drafts(
            template, [{"speaker_id": speaker.pk}]
        )
        assert mails == []
        assert render_failures == 1
        assert event.queued_mails.count() == 0
