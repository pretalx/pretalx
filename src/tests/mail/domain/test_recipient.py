# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scopes_disabled

from pretalx.mail.domain.recipient import Recipient
from tests.factories import EventFactory, SpeakerFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_recipient_wraps_bare_user():
    event = EventFactory(locale="en", locales=["en"])
    user = UserFactory(name="Jane Doe", locale="de")

    recipient = Recipient(user)

    assert recipient.user == user
    assert recipient.email == user.email
    assert recipient.name == "Jane Doe"
    assert recipient.locale == "de"
    assert recipient.get_locale_for_event(event) == "en"


def test_recipient_wraps_speaker_profile():
    with scopes_disabled():
        speaker = SpeakerFactory(user=None, email="managed@example.com", locale=None)

    recipient = Recipient(speaker)

    assert recipient.user is None
    assert recipient.email == "managed@example.com"
    assert recipient.locale == speaker.event.locale
    assert recipient.get_locale_for_event(speaker.event) == speaker.event.locale
    assert recipient.speaker(speaker.event) == speaker


def test_recipient_speaker_resolves_per_event():
    event = EventFactory()
    other_event = EventFactory()
    user = UserFactory()
    assert Recipient(None).speaker(event) is None
    assert Recipient(user).speaker(event) is None

    with scopes_disabled():
        speaker = SpeakerFactory(user=user, event=event)

    assert Recipient(user).speaker(event) == speaker
    assert Recipient(speaker).speaker(event) == speaker
    assert Recipient(speaker).speaker(other_event) is None


def test_recipient_equality_and_hash():
    with scopes_disabled():
        speaker = SpeakerFactory()

    assert Recipient(speaker) == Recipient(speaker)
    assert Recipient(speaker) != Recipient(speaker.user)
    assert hash(Recipient(speaker)) == hash(Recipient(speaker))
    assert "Recipient(" in repr(Recipient(speaker))
