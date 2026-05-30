# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import uuid

import pytest
from django.db.utils import IntegrityError
from django.utils.translation import gettext_lazy as _
from django_scopes import scope

from pretalx.common.models.settings import GlobalSettings
from pretalx.person.models.profile import SpeakerProfile
from tests.factories import (
    AnswerFactory,
    AvailabilityFactory,
    EventFactory,
    QuestionFactory,
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


@pytest.mark.parametrize(
    "accessor", ("talks", "current_talk_slots"), ids=["talks", "current_talk_slots"]
)
def test_speaker_profile_no_schedule_returns_empty(event, accessor):
    speaker = SpeakerFactory(event=event)
    with scope(event=event):
        assert list(getattr(speaker, accessor)) == []


def test_speaker_profile_reviewer_answers_filters_visible(event):
    speaker = SpeakerFactory(event=event)
    q_visible = QuestionFactory(
        event=event, target="speaker", is_visible_to_reviewers=True
    )
    q_hidden = QuestionFactory(
        event=event, target="speaker", is_visible_to_reviewers=False
    )
    visible_answer = AnswerFactory(question=q_visible, speaker=speaker, submission=None)
    AnswerFactory(question=q_hidden, speaker=speaker, submission=None)

    assert list(speaker.reviewer_answers) == [visible_answer]


def test_speaker_profile_get_instance_data_with_pk(event):
    speaker = SpeakerFactory(event=event, name="Alice")
    data = speaker.get_instance_data()

    assert data["name"] == "Alice"
    assert data["email"] == speaker.user.email


def test_speaker_profile_get_instance_data_without_pk():
    """Without a pk, the profile-specific email override is not added."""
    speaker = SpeakerProfile(event=EventFactory(), user=None, name=None)
    speaker.pk = None
    data = speaker.get_instance_data()
    assert "email" not in data


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
    """Overlapping availabilities are merged into a single range."""
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


def test_speaker_guid_none_without_user_or_code():
    assert SpeakerProfile(event=EventFactory(), user=None).guid is None
