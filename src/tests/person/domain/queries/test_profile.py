# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.person.domain.queries.profile import (
    annotate_speaker_submission_counts,
    annotate_user_submission_counts,
    filter_by_accepted_role,
    other_speaker_profiles,
)
from pretalx.person.models import SpeakerProfile, User
from tests.factories import EventFactory, SpeakerFactory, SubmissionFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_other_speaker_profiles_returns_user_profiles_on_other_events():
    user = UserFactory()
    current_event = EventFactory()
    other_event = EventFactory()
    current = SpeakerFactory(user=user, event=current_event, biography="here")
    other = SpeakerFactory(user=user, event=other_event, biography="there")

    result = list(other_speaker_profiles(current))

    assert result == [other]
    assert current not in result


def test_other_speaker_profiles_excludes_other_users():
    user = UserFactory()
    other_user = UserFactory()
    event = EventFactory()
    profile = SpeakerFactory(user=user, event=event)
    SpeakerFactory(user=other_user, event=event)

    assert list(other_speaker_profiles(profile)) == []


def test_annotate_speaker_submission_counts_counts_per_event():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    accepted = SubmissionFactory(event=event, state="accepted")
    accepted.speakers.add(speaker)
    rejected = SubmissionFactory(event=event, state="rejected")
    rejected.speakers.add(speaker)

    qs = annotate_speaker_submission_counts(
        SpeakerProfile.objects.filter(pk=speaker.pk), event=event
    )
    result = qs.get()

    assert result.submission_count == 2
    assert result.accepted_submission_count == 1


def test_annotate_user_submission_counts_counts_per_events():
    event = EventFactory()
    user = UserFactory()
    profile = SpeakerFactory(user=user, event=event)
    accepted = SubmissionFactory(event=event, state="accepted")
    accepted.speakers.add(profile)

    qs = annotate_user_submission_counts(
        User.objects.filter(pk=user.pk), events=[event]
    )
    result = qs.get()

    assert result.submission_count == 1
    assert result.accepted_submission_count == 1


@pytest.mark.parametrize(
    ("role", "expect_with_accepted", "expect_without_accepted"),
    (
        ("speaker", True, False),
        ("submitter", False, True),
        ("all", True, True),
        ("", True, True),
    ),
)
def test_filter_by_accepted_role(role, expect_with_accepted, expect_without_accepted):
    event = EventFactory()
    with_accepted = SpeakerFactory(event=event)
    accepted = SubmissionFactory(event=event, state="accepted")
    accepted.speakers.add(with_accepted)
    without_accepted = SpeakerFactory(event=event)

    qs = annotate_speaker_submission_counts(
        SpeakerProfile.objects.filter(event=event), event=event
    )
    filtered = set(filter_by_accepted_role(qs, role))

    expected = set()
    if expect_with_accepted:
        expected.add(with_accepted)
    if expect_without_accepted:
        expected.add(without_accepted)
    assert filtered == expected
