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


def _form_data(to, subject="Test", text="Body"):
    return {
        "to": to,
        "reply_to": "",
        "cc": "",
        "bcc": "",
        "subject": subject,
        "text": text,
    }


def test_mail_detail_form_offers_reachable_speakers_only_when_mail_has_some():
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
    address_only_mail = QueuedMailFactory(event=event, to="test@example.com")

    form = MailDetailForm(instance=mail)

    assert form.fields["to_speakers"].required is False
    assert set(form.fields["to_speakers"].queryset) == {
        account_backed,
        managed_with_email,
    }
    assert "to_speakers" not in MailDetailForm(instance=address_only_mail).fields


def test_mail_detail_form_clean_no_recipients():
    event = EventFactory()
    mail = QueuedMailFactory(event=event, to="someone@example.com")
    form = MailDetailForm(instance=mail, data=_form_data(to=""))

    assert not form.is_valid()
    assert "to" in form.errors


def test_mail_detail_form_save_clears_text_html_only_on_text_change():
    # Edited plain text invalidates the stored HTML body so delivery_html
    # regenerates from self.text at send time.
    event = EventFactory()
    mail = QueuedMailFactory(
        event=event,
        to="someone@example.com",
        subject="Original subject",
        text="Body",
        text_html="<p>Body rendered</p>",
    )

    form = MailDetailForm(
        instance=mail, data=_form_data("someone@example.com", "New subject", "Body")
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    saved.refresh_from_db()

    assert saved.subject == "New subject"
    assert saved.text_html == "<p>Body rendered</p>"

    form = MailDetailForm(
        instance=saved,
        data=_form_data("someone@example.com", "New subject", "Edited body"),
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    saved.refresh_from_db()

    assert saved.text == "Edited body"
    assert saved.text_html is None


@pytest.mark.parametrize(
    ("to", "expected_to", "expected_speakers"),
    (
        ("old@example.com", "old@example.com", []),
        ("unknown@example.com", "unknown@example.com", []),
        ("known@example.com", "", ["account"]),
        ("managed@example.com,unknown@example.com", "unknown@example.com", ["managed"]),
        ("FOO@Example.Com,foo@example.com", "foo@example.com", []),
    ),
    ids=("unchanged", "unknown", "known_account", "mixed_managed", "case_dedup"),
)
def test_mail_detail_form_save_moves_known_addresses_to_speakers(
    to, expected_to, expected_speakers
):
    event = EventFactory()
    speakers = {
        "account": SpeakerFactory(
            event=event,
            user=UserFactory(email="known@example.com"),
            origin=SpeakerProfileOrigin.ORGA,
        ),
        "managed": SpeakerFactory(
            event=event,
            user=None,
            email="managed@example.com",
            origin=SpeakerProfileOrigin.ORGA,
        ),
    }
    mail = QueuedMailFactory(event=event, to="old@example.com")
    form = MailDetailForm(instance=mail, data=_form_data(to, subject="Updated"))
    assert form.is_valid(), form.errors

    saved = form.save()
    saved.refresh_from_db()

    assert saved.subject == "Updated"
    assert saved.to == expected_to
    assert list(saved.to_speakers.all()) == [speakers[key] for key in expected_speakers]
