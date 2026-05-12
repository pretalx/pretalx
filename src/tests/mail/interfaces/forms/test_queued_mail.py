# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.interfaces.forms.queued_mail import (
    MailDetailForm,
    QueuedMailFilterForm,
)
from tests.factories import (
    EventFactory,
    QueuedMailFactory,
    SpeakerFactory,
    SubmissionFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_mail_detail_form_init_no_to_users_removes_field():
    event = EventFactory()
    mail = QueuedMailFactory(event=event, to="test@example.com")

    form = MailDetailForm(instance=mail)

    assert "to_users" not in form.fields


def test_mail_detail_form_init_with_to_users_keeps_field():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    mail = QueuedMailFactory(event=event, to="")
    mail.to_users.add(speaker.user)

    form = MailDetailForm(instance=mail)

    assert "to_users" in form.fields
    assert form.fields["to_users"].required is False


def test_mail_detail_form_clean_no_recipients():
    event = EventFactory()
    mail = QueuedMailFactory(event=event, to="someone@example.com")
    form = MailDetailForm(
        instance=mail,
        data={
            "to": "",
            "reply_to": "",
            "cc": "",
            "bcc": "",
            "subject": "Test",
            "text": "Body",
        },
    )

    assert not form.is_valid()
    assert "to" in form.errors


def test_mail_detail_form_save_clears_text_html_on_text_change():
    # Edited plain text invalidates the stored HTML body so delivery_html
    # regenerates from self.text at send time.
    event = EventFactory()
    mail = QueuedMailFactory(
        event=event,
        to="someone@example.com",
        text="Original body",
        text_html="<p>Original body rendered</p>",
    )

    form = MailDetailForm(
        instance=mail,
        data={
            "to": "someone@example.com",
            "reply_to": "",
            "cc": "",
            "bcc": "",
            "subject": mail.subject,
            "text": "Edited body",
        },
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    saved.refresh_from_db()

    assert saved.text == "Edited body"
    assert saved.text_html is None


def test_mail_detail_form_save_keeps_text_html_when_only_subject_edited():
    event = EventFactory()
    mail = QueuedMailFactory(
        event=event,
        to="someone@example.com",
        subject="Original subject",
        text="Body",
        text_html="<p>Body rendered</p>",
    )

    form = MailDetailForm(
        instance=mail,
        data={
            "to": "someone@example.com",
            "reply_to": "",
            "cc": "",
            "bcc": "",
            "subject": "New subject",
            "text": "Body",
        },
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    saved.refresh_from_db()

    assert saved.subject == "New subject"
    assert saved.text_html == "<p>Body rendered</p>"


def test_mail_detail_form_clean_with_to_address():
    event = EventFactory()
    mail = QueuedMailFactory(event=event, to="someone@example.com")
    form = MailDetailForm(
        instance=mail,
        data={
            "to": "recipient@example.com",
            "reply_to": "",
            "cc": "",
            "bcc": "",
            "subject": "Test",
            "text": "Body",
        },
    )

    assert form.is_valid(), form.errors


def test_mail_detail_form_save_moves_known_address_to_to_users():
    event = EventFactory()
    user = UserFactory(email="known@example.com")
    mail = QueuedMailFactory(event=event, to="old@example.com")
    form = MailDetailForm(
        instance=mail,
        data={
            "to": "known@example.com",
            "reply_to": "",
            "cc": "",
            "bcc": "",
            "subject": "Test",
            "text": "Body",
        },
    )
    assert form.is_valid(), form.errors

    saved = form.save()
    saved.refresh_from_db()

    assert saved.to == ""
    assert list(saved.to_users.all()) == [user]


def test_mail_detail_form_save_keeps_unknown_address_in_to():
    event = EventFactory()
    mail = QueuedMailFactory(event=event, to="old@example.com")
    form = MailDetailForm(
        instance=mail,
        data={
            "to": "unknown@example.com",
            "reply_to": "",
            "cc": "",
            "bcc": "",
            "subject": "Test",
            "text": "Body",
        },
    )
    assert form.is_valid(), form.errors

    saved = form.save()
    saved.refresh_from_db()

    assert saved.to == "unknown@example.com"
    assert list(saved.to_users.all()) == []


def test_mail_detail_form_save_mixed_known_and_unknown():
    event = EventFactory()
    user = UserFactory(email="known@example.com")
    mail = QueuedMailFactory(event=event, to="old@example.com")
    form = MailDetailForm(
        instance=mail,
        data={
            "to": "known@example.com,unknown@example.com",
            "reply_to": "",
            "cc": "",
            "bcc": "",
            "subject": "Test",
            "text": "Body",
        },
    )
    assert form.is_valid(), form.errors

    saved = form.save()
    saved.refresh_from_db()

    assert saved.to == "unknown@example.com"
    assert list(saved.to_users.all()) == [user]


def test_mail_detail_form_save_normalizes_email_case():
    event = EventFactory()
    mail = QueuedMailFactory(event=event, to="old@example.com")
    form = MailDetailForm(
        instance=mail,
        data={
            "to": "FOO@Example.Com,foo@example.com",
            "reply_to": "",
            "cc": "",
            "bcc": "",
            "subject": "Test",
            "text": "Body",
        },
    )
    assert form.is_valid(), form.errors

    saved = form.save()
    saved.refresh_from_db()

    assert saved.to == "foo@example.com"


def test_mail_detail_form_save_without_to_change():
    event = EventFactory()
    mail = QueuedMailFactory(event=event, to="test@example.com")
    form = MailDetailForm(
        instance=mail,
        data={
            "to": "test@example.com",
            "reply_to": "",
            "cc": "",
            "bcc": "",
            "subject": "Updated subject",
            "text": "Updated body",
        },
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    saved.refresh_from_db()
    assert saved.subject == "Updated subject"
    assert saved.to == "test@example.com"


def test_queued_mail_filter_form_init_sent_removes_status():
    event = EventFactory()
    form = QueuedMailFilterForm(event=event, sent=True)

    assert "status" not in form.fields


def test_queued_mail_filter_form_init_no_failed_removes_status():
    event = EventFactory()
    form = QueuedMailFilterForm(event=event, sent=False)

    assert "status" not in form.fields


def test_queued_mail_filter_form_init_with_failed_shows_status():
    event = EventFactory()
    QueuedMailFactory(
        event=event,
        state=QueuedMailStates.DRAFT,
        error_data={"error": "SMTP failed", "type": "Exception"},
    )
    QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    form = QueuedMailFilterForm(event=event, sent=False)

    assert "status" in form.fields
    choice_values = [v for v, _ in form.fields["status"].choices]
    assert choice_values == ["draft", "failed"]


def test_queued_mail_filter_form_init_no_tracks_removes_track():
    event = EventFactory(feature_flags={"use_tracks": False})
    form = QueuedMailFilterForm(event=event, sent=False)

    assert "track" not in form.fields


def test_queued_mail_filter_form_init_with_tracks_shows_track():
    event = EventFactory()
    track = TrackFactory(event=event)
    form = QueuedMailFilterForm(event=event, sent=False)

    assert "track" in form.fields
    assert track in form.fields["track"].queryset


def test_queued_mail_filter_form_filter_queryset_by_status():
    event = EventFactory()
    failed = QueuedMailFactory(
        event=event,
        state=QueuedMailStates.DRAFT,
        error_data={"error": "fail", "type": "Exception"},
    )
    QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    form = QueuedMailFilterForm(event=event, sent=False, data={"status": ["failed"]})
    assert form.is_valid(), form.errors

    qs = event.queued_mails.filter(state=QueuedMailStates.DRAFT).with_computed_state()
    result = list(form.filter_queryset(qs))

    assert result == [failed]


def test_queued_mail_filter_form_filter_queryset_by_track():
    event = EventFactory()
    track = TrackFactory(event=event)
    submission = SubmissionFactory(event=event, track=track)
    mail_with_track = QueuedMailFactory(event=event)
    mail_with_track.submissions.add(submission)
    QueuedMailFactory(event=event)
    form = QueuedMailFilterForm(event=event, sent=False, data={"track": [track.pk]})
    assert form.is_valid(), form.errors

    result = list(form.filter_queryset(event.queued_mails.all()))

    assert result == [mail_with_track]


def test_queued_mail_filter_form_filter_queryset_no_filters():
    event = EventFactory()
    mail = QueuedMailFactory(event=event)
    form = QueuedMailFilterForm(event=event, sent=True, data={})
    assert form.is_valid(), form.errors

    result = list(form.filter_queryset(event.queued_mails.all()))

    assert result == [mail]


def test_queued_mail_filter_form_init_sent_none_with_tracks():
    """When sent=None and tracks enabled, track filter uses unfiltered mail count."""
    event = EventFactory()
    TrackFactory(event=event)
    form = QueuedMailFilterForm(event=event, sent=None)

    assert "track" in form.fields


def test_queued_mail_filter_form_init_sent_true_with_tracks_counts_sent_mails():
    """sent=True annotates the track queryset using SENT/SENDING mails only."""
    event = EventFactory()
    track = TrackFactory(event=event)
    other_track = TrackFactory(event=event)
    submission = SubmissionFactory(event=event, track=track)
    sent_mail = QueuedMailFactory(event=event, state=QueuedMailStates.SENT)
    sent_mail.submissions.add(submission)
    draft_mail = QueuedMailFactory(event=event, state=QueuedMailStates.DRAFT)
    draft_mail.submissions.add(SubmissionFactory(event=event, track=other_track))

    form = QueuedMailFilterForm(event=event, sent=True)

    counts = {t.pk: t.mail_count for t in form.fields["track"].queryset}
    assert counts[track.pk] == 1
    assert counts[other_track.pk] == 0
