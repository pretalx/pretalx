# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scope

from pretalx.person.enums import SpeakerProfileOrigin
from pretalx.submission.domain.queries.speaker import speakers_for_user
from tests.factories import (
    EventFactory,
    SpeakerFactory,
    SubmissionFactory,
    TeamFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_speakers_for_user():
    event = EventFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    user = UserFactory()
    team.members.add(user)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)

    with scope(event=event):
        result = speakers_for_user(event, user)

    assert speaker in result


def test_speakers_for_user_excludes_bare_profiles_by_default():
    event = EventFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    user = UserFactory()
    team.members.add(user)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    SpeakerFactory(event=event, user=None, origin=SpeakerProfileOrigin.ORGA)

    with scope(event=event):
        result = speakers_for_user(event, user)

    assert list(result) == [speaker]


def test_speakers_for_user_include_bare():
    event = EventFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    user = UserFactory()
    team.members.add(user)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    bare_orga = SpeakerFactory(event=event, user=None, origin=SpeakerProfileOrigin.ORGA)
    SpeakerFactory(event=event, user=None, origin=SpeakerProfileOrigin.CFP)

    with scope(event=event):
        result = speakers_for_user(event, user, include_bare=True)

    assert set(result) == {speaker, bare_orga}


def test_speakers_for_user_prefetch_submissions(django_assert_num_queries):
    event = EventFactory()
    team = TeamFactory(
        organiser=event.organiser, all_events=True, can_change_submissions=True
    )
    user = UserFactory()
    team.members.add(user)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)

    with scope(event=event):
        speakers = list(speakers_for_user(event, user, prefetch_submissions=True))
        # Submissions are prefetched, so iterating .submissions costs no
        # additional query.
        with django_assert_num_queries(0):
            for s in speakers:
                list(s.submissions.all())
