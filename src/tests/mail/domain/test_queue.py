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


def test_copy_to_draft_preserves_to_speakers(event):
    with scope(event=event):
        speaker = SpeakerFactory(event=event)
        original = QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
        original.to_speakers.add(speaker)

        copy = copy_to_draft(original)

        assert list(copy.to_speakers.all()) == [speaker]


def test_copy_to_draft_drops_unreachable_speakers(event):
    with scope(event=event):
        reachable = SpeakerFactory(event=event)
        managed = SpeakerFactory(event=event, user=None, email=None, name="No Mail")
        original = QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
        original.to_speakers.add(reachable, managed)

        copy = copy_to_draft(original)

        assert copy.pk != original.pk
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


def test_bulk_create_drafts_skips_missing_speaker(event):
    template = MailTemplateFactory(event=event)
    with scope(event=event):
        mails, render_failures = bulk_create_drafts(template, [{"speaker_id": 999999}])
        assert mails == []
        assert render_failures == 0
        assert event.queued_mails.count() == 0


def test_bulk_create_drafts_persists_one_per_unique_recipient(event):
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    speaker = SpeakerFactory(event=event)
    with scope(event=event):
        mails, render_failures = bulk_create_drafts(
            template, [{"speaker_id": speaker.pk}]
        )
    assert render_failures == 0
    assert len(mails) == 1
    mail = mails[0]
    assert mail.pk is not None
    assert mail.state == QueuedMailStates.DRAFT
    assert mail.subject == "Hi"
    assert mail.text == "Body"
    with scope(event=event):
        assert list(mail.to_speakers.all()) == [speaker]
        assert list(mail.submissions.all()) == []


def test_bulk_create_drafts_renders_event_speaker_name(event):
    template = MailTemplateFactory(event=event, subject="Hi", text="Hi {name},")
    speaker = SpeakerFactory(event=event, name="Jane Doe")
    speaker.user.name = "j-doe"
    speaker.user.save()
    with scope(event=event):
        mails, render_failures = bulk_create_drafts(
            template, [{"speaker_id": speaker.pk}]
        )
    assert render_failures == 0
    assert mails[0].text == "Hi Jane Doe,"


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


def test_bulk_create_drafts_skips_legacy_user_without_profile(event):
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    user = UserFactory()
    with scope(event=event):
        mails, render_failures = bulk_create_drafts(template, [{"user_id": user.pk}])
        assert mails == []
        assert render_failures == 0
        assert event.queued_mails.count() == 0


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
    assert str(slot.room.name) in mails[0].text


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


def test_bulk_create_drafts_progress_callback_fires_per_recipient(event):
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    speaker = SpeakerFactory(event=event)
    progress_calls = []
    with scope(event=event):
        bulk_create_drafts(
            template,
            [{"speaker_id": speaker.pk}, {"speaker_id": 999999}],
            progress=lambda current, total: progress_calls.append((current, total)),
        )
    assert progress_calls == [(1, 2), (2, 2)]


def test_bulk_create_drafts_drops_unreachable_speaker(event):
    template = MailTemplateFactory(event=event, subject="Hi", text="Body")
    with scope(event=event):
        managed = SpeakerFactory(event=event, user=None, email=None, name="No Mail")

        mails, render_failures = bulk_create_drafts(
            template, [{"speaker_id": managed.pk}]
        )

        assert mails == []
        assert render_failures == 0
        assert event.queued_mails.count() == 0
