# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import uuid

import pytest
from django.db.utils import IntegrityError
from django.utils.translation import gettext_lazy as _
from django_scopes import scope

from pretalx.common.models.mixins import GenerateCode
from pretalx.common.models.settings import GlobalSettings
from pretalx.person.enums import SpeakerProfileOrigin
from pretalx.person.models.profile import SpeakerProfile
from tests.factories import (
    AvailabilityFactory,
    EventFactory,
    SpeakerFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_speaker_profile_str():
    speaker = SpeakerFactory(name="Alice")
    assert str(speaker) == f"SpeakerProfile(event={speaker.event.slug}, user=Alice)"


def test_speaker_profile_str_unnamed():
    speaker = SpeakerFactory(name=None)
    speaker.user.name = ""
    expected = (
        f"SpeakerProfile(event={speaker.event.slug}, user={speaker.get_display_name()})"
    )
    assert str(speaker) == expected


def test_speaker_profile_get_display_name_profile_name():
    speaker = SpeakerFactory(name="Profile Name")
    assert speaker.get_display_name() == "Profile Name"


def test_speaker_profile_get_display_name_user_name():
    speaker = SpeakerFactory(name=None)
    speaker.user.name = "User Name"
    assert speaker.get_display_name() == "User Name"


def test_speaker_profile_get_display_name_no_user():
    speaker = SpeakerFactory(user=None, name=None)
    assert speaker.get_display_name() == str(_("Unnamed speaker"))


def test_speaker_profile_get_display_name_fallback():
    speaker = SpeakerFactory(name=None)
    speaker.user.name = ""
    assert speaker.get_display_name() == str(_("Unnamed speaker"))


def test_speaker_profile_get_display_name_allow_empty():
    speaker = SpeakerFactory(user=None, name=None)
    assert speaker.get_display_name(allow_empty=True) == ""


def test_speaker_profile_get_display_name_allow_empty_with_name():
    speaker = SpeakerFactory(name="Profile Name")
    assert speaker.get_display_name(allow_empty=True) == "Profile Name"


@pytest.mark.parametrize(
    "accessor", ("talks", "current_talk_slots"), ids=["talks", "current_talk_slots"]
)
def test_speaker_profile_no_schedule_returns_empty(event, accessor):
    speaker = SpeakerFactory(event=event)
    with scope(event=event):
        assert list(getattr(speaker, accessor)) == []


def test_speaker_profile_get_instance_data_with_pk(event):
    speaker = SpeakerFactory(event=event, name="Alice", email="contact@example.com")
    data = speaker.get_instance_data()

    assert data["name"] == "Alice"
    assert data["email"] == "contact@example.com"
    assert data["user_email"] == speaker.user.email


def test_speaker_profile_get_instance_data_managed(event):
    speaker = SpeakerFactory(event=event, user=None, name="Alice")
    data = speaker.get_instance_data()

    assert data["name"] == "Alice"
    assert data["email"] is None
    assert data["user_email"] is None


def test_speaker_profile_get_instance_data_without_pk():
    speaker = SpeakerProfile(event=EventFactory(), user=UserFactory(), name=None)
    speaker.pk = None
    data = speaker.get_instance_data()
    assert data["email"] is None


def test_speaker_profile_get_instance_data_excludes_invitation_token(event):
    speaker = SpeakerFactory(event=event)
    speaker.invitation_token = "very-secret-claim-token"
    speaker.save()

    data = speaker.get_instance_data()

    assert "invitation_token" not in data


def test_speaker_profile_get_instance_data_profile_picture_none(event):
    speaker = SpeakerFactory(event=event)
    data = speaker.get_instance_data()
    assert data["profile_picture"] is None


def test_speaker_profile_unique_event_user():
    speaker = SpeakerFactory()
    with pytest.raises(IntegrityError):
        SpeakerFactory(event=speaker.event, user=speaker.user)


def test_speaker_profile_unique_event_code():
    speaker = SpeakerFactory()
    with pytest.raises(IntegrityError):
        SpeakerProfile.objects.create(event=speaker.event, user=None, code=speaker.code)


def test_speaker_profile_full_availability_empty(event):
    speaker = SpeakerFactory(event=event)
    with scope(event=event):
        result = speaker.full_availability
    assert result == []


def test_speaker_profile_full_availability_with_data(event):
    speaker = SpeakerFactory(event=event)
    avail = AvailabilityFactory(event=event, person=speaker)

    with scope(event=event):
        result = speaker.full_availability

    assert len(result) == 1
    assert result[0].start == avail.start
    assert result[0].end == avail.end


def test_speaker_profile_full_availability_merges_overlapping(event):
    speaker = SpeakerFactory(event=event)
    start = event.datetime_from
    mid = start + (event.datetime_to - start) / 2
    AvailabilityFactory(event=event, person=speaker, start=start, end=mid)
    AvailabilityFactory(event=event, person=speaker, start=mid, end=event.datetime_to)

    with scope(event=event):
        result = speaker.full_availability

    assert len(result) == 1
    assert result[0].start == start
    assert result[0].end == event.datetime_to


def test_speaker_guid_derived_from_user_code():
    speaker = SpeakerFactory(user=UserFactory())
    expected = str(
        uuid.uuid5(
            GlobalSettings().get_instance_identifier(), f"user:{speaker.user.code}"
        )
    )
    assert speaker.guid == expected


def test_speaker_guid_without_user_uses_own_code():
    speaker = SpeakerFactory(user=None)
    expected = str(
        uuid.uuid5(
            GlobalSettings().get_instance_identifier(), f"speaker:{speaker.code}"
        )
    )
    assert speaker.guid == expected


def test_speaker_guid_stable_for_user_across_events():
    user = UserFactory()
    assert SpeakerFactory(user=user).guid == SpeakerFactory(user=user).guid


def test_speaker_guid_different_speakers():
    assert SpeakerFactory().guid != SpeakerFactory().guid


def test_speaker_guid_not_computable_without_user_or_code():
    assert SpeakerProfile(event=EventFactory(), user=None).compute_guid() is None


def test_speaker_guid_persisted_at_creation():
    speaker = SpeakerFactory(user=None)
    stored = SpeakerProfile.objects.get(pk=speaker.pk).guid
    expected = str(
        uuid.uuid5(
            GlobalSettings().get_instance_identifier(), f"speaker:{speaker.code}"
        )
    )
    assert stored == expected


def test_speaker_guid_and_origin_survive_claim():
    speaker = SpeakerFactory(user=None, origin=SpeakerProfileOrigin.ORGA)
    old_guid = speaker.guid

    speaker.user = UserFactory()
    speaker.save()
    speaker.refresh_from_db()

    assert speaker.guid == old_guid
    assert speaker.origin == SpeakerProfileOrigin.ORGA


def test_speaker_profile_origin_defaults_to_cfp():
    assert SpeakerFactory().origin == SpeakerProfileOrigin.CFP


@pytest.mark.parametrize(
    ("profile_email", "with_user", "expected"),
    (
        ("contact@example.com", False, "contact@example.com"),
        (None, False, None),
        ("contact@example.com", True, "contact@example.com"),
        (None, True, "account@example.com"),
    ),
    ids=[
        "managed_with_email",
        "managed_without_email",
        "override_beats_account",
        "account_fallback",
    ],
)
def test_speaker_profile_effective_email(profile_email, with_user, expected):
    user = UserFactory(email="account@example.com") if with_user else None
    speaker = SpeakerFactory(user=user, email=profile_email)
    assert speaker.effective_email == expected


def test_speaker_profile_effective_email_follows_account_change():
    speaker = SpeakerFactory(email=None)
    speaker.user.email = "changed@example.com"
    assert speaker.effective_email == "changed@example.com"


def test_speaker_profile_duplicate_contact_emails_allowed():
    event = EventFactory()
    SpeakerFactory(event=event, user=None, email="agency@example.com")
    SpeakerFactory(event=event, user=None, email="agency@example.com")

    with scope(event=event):
        count = SpeakerProfile.objects.filter(email="agency@example.com").count()
    assert count == 2


@pytest.mark.parametrize(
    ("profile_locale", "user_locale", "expected"),
    (("de", "en", "de"), (None, "de", "de"), ("fr", "de", "en"), (None, "fr", "en")),
    ids=[
        "profile_locale_wins",
        "account_fallback",
        "dropped_profile_locale_uses_event_default",
        "unoffered_account_locale_uses_event_default",
    ],
)
def test_speaker_profile_effective_locale_with_account(
    profile_locale, user_locale, expected
):
    event = EventFactory(locales=["en", "de"], locale="en")
    speaker = SpeakerFactory(
        event=event, user=UserFactory(locale=user_locale), locale=profile_locale
    )
    assert speaker.effective_locale == expected


@pytest.mark.parametrize(
    ("profile_locale", "expected"),
    (("de", "de"), (None, "en"), ("fr", "en")),
    ids=["profile_locale", "event_default", "dropped_locale_uses_event_default"],
)
def test_speaker_profile_effective_locale_managed(profile_locale, expected):
    event = EventFactory(locales=["en", "de"], locale="en")
    speaker = SpeakerFactory(event=event, user=None, locale=profile_locale)
    assert speaker.effective_locale == expected


def test_speaker_managed_code_collision_retry_keeps_guid_in_sync(monkeypatch):
    event = EventFactory()
    existing = SpeakerFactory(event=event, user=None)
    existing_code = existing.code

    call_count = 0
    original_assign = GenerateCode.assign_code

    def assign_with_collision(self, length=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            self.code = existing_code
        else:
            original_assign(self, length=length)

    monkeypatch.setattr(GenerateCode, "assign_code", assign_with_collision)
    speaker = SpeakerFactory(event=event, user=None)

    assert speaker.code != existing_code
    assert call_count == 2
    assert speaker.guid == str(
        uuid.uuid5(
            GlobalSettings().get_instance_identifier(), f"speaker:{speaker.code}"
        )
    )


def test_speaker_guid_recomputed_on_partial_save():
    speaker = SpeakerFactory()
    with scope(event=speaker.event):
        SpeakerProfile.objects.filter(pk=speaker.pk).update(guid="")
    speaker.refresh_from_db()
    assert not speaker.guid

    speaker.name = "New Name"
    speaker.save(update_fields=["name"])

    speaker.refresh_from_db()
    assert speaker.name == "New Name"
    assert speaker.guid == speaker.compute_guid()
