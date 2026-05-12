# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scope

from pretalx.person.domain.queries.user import (
    submitter_users_for_events,
    with_profiles,
    with_speaker_code,
)
from pretalx.person.models import User
from pretalx.submission.models import SubmissionStates
from tests.factories import EventFactory, SpeakerFactory, SubmissionFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_with_profiles_prefetches_speakers(event, django_assert_num_queries):
    speaker = SpeakerFactory(event=event)

    users = list(with_profiles(User.objects.all(), event).filter(pk=speaker.user.pk))

    assert len(users) == 1
    with django_assert_num_queries(0):
        speakers = users[0]._speakers
    assert speakers[0].pk == speaker.pk


def test_with_speaker_code_annotates_code(event):
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)

    users = list(
        with_speaker_code(User.objects.all(), event).filter(pk=speaker.user.pk)
    )

    assert len(users) == 1
    assert users[0].speaker_code == speaker.code


def test_with_speaker_code_no_submissions(event):
    speaker = SpeakerFactory(event=event)

    users = list(
        with_speaker_code(User.objects.all(), event).filter(pk=speaker.user.pk)
    )

    assert len(users) == 1
    assert users[0].speaker_code is None


def test_submitter_users_for_events_spans_multiple_events():
    """Users who have a non-draft submission in any of the given events show
    up exactly once across the queryset."""
    event_a = EventFactory()
    event_b = EventFactory()
    user = UserFactory()
    with scope(event=event_a):
        profile_a = SpeakerFactory(user=user, event=event_a)
        sub_a = SubmissionFactory(event=event_a, state=SubmissionStates.SUBMITTED)
        sub_a.speakers.add(profile_a)
    with scope(event=event_b):
        profile_b = SpeakerFactory(user=user, event=event_b)
        sub_b = SubmissionFactory(event=event_b, state=SubmissionStates.ACCEPTED)
        sub_b.speakers.add(profile_b)

    result = list(submitter_users_for_events([event_a, event_b]))

    assert result == [user]


def test_submitter_users_for_events_excludes_profile_only_users():
    event = EventFactory()
    with scope(event=event):
        SpeakerFactory(event=event)

    assert list(submitter_users_for_events([event])) == []


def test_submitter_users_for_events_excludes_draft_only_users():
    event = EventFactory()
    user = UserFactory()
    with scope(event=event):
        profile = SpeakerFactory(user=user, event=event)
        draft = SubmissionFactory(event=event, state=SubmissionStates.DRAFT)
        draft.speakers.add(profile)

    assert list(submitter_users_for_events([event])) == []


def test_submitter_users_for_events_ignores_submissions_outside_events():
    in_event = EventFactory()
    out_event = EventFactory()
    user = UserFactory()
    with scope(event=out_event):
        profile = SpeakerFactory(user=user, event=out_event)
        sub = SubmissionFactory(event=out_event, state=SubmissionStates.SUBMITTED)
        sub.speakers.add(profile)

    assert list(submitter_users_for_events([in_event])) == []
