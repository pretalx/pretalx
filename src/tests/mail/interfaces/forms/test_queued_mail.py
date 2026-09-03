# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.mail.interfaces.forms.queued_mail import MailDetailForm
from pretalx.person.enums import SpeakerProfileOrigin
from tests.factories import (
    EventFactory,
    QueuedMailFactory,
    SpeakerFactory,
    SubmissionFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_mail_detail_form_init_no_to_speakers_removes_field():
    event = EventFactory()
    mail = QueuedMailFactory(event=event, to="test@example.com")

    form = MailDetailForm(instance=mail)

    assert "to_speakers" not in form.fields


def test_mail_detail_form_to_speakers_queryset_only_reachable():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    account_backed = SpeakerFactory(event=event)
    managed_with_email = SpeakerFactory(
        event=event, user=None, email="managed@example.com"
    )
    managed_without_email = SpeakerFactory(event=event, user=None, email=None)
    submission.speakers.add(account_backed, managed_with_email, managed_without_email)
    mail = QueuedMailFactory(event=event, to="")
    mail.to_speakers.add(account_backed)

    form = MailDetailForm(instance=mail)

    assert form.fields["to_speakers"].required is False
    assert set(form.fields["to_speakers"].queryset) == {
        account_backed,
        managed_with_email,
    }


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


def test_mail_detail_form_save_moves_known_address_to_to_speakers():
    event = EventFactory()
    speaker = SpeakerFactory(
        event=event,
        user=UserFactory(email="known@example.com"),
        origin=SpeakerProfileOrigin.ORGA,
    )
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
    assert list(saved.to_speakers.all()) == [speaker]


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
    assert list(saved.to_speakers.all()) == []


def test_mail_detail_form_save_mixed_known_and_unknown():
    event = EventFactory()
    speaker = SpeakerFactory(
        event=event,
        user=None,
        email="known@example.com",
        origin=SpeakerProfileOrigin.ORGA,
    )
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
    assert list(saved.to_speakers.all()) == [speaker]


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
