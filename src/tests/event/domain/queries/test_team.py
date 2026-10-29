# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.event.domain.queries.team import (
    active_reviewers_for_event,
    event_reviewer_teams,
    speaker_access_events_for_user,
    user_reviewer_teams_in_event,
    user_teams_in_organiser,
)
from tests.factories import (
    EventFactory,
    OrganiserFactory,
    ReviewFactory,
    SubmissionFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_user_teams_in_organiser_returns_user_teams_of_that_organiser_filtered():
    organiser = OrganiserFactory()
    other = OrganiserFactory()
    user = UserFactory()
    matching = TeamFactory(organiser=organiser, can_change_teams=True)
    matching.members.add(user)
    non_matching = TeamFactory(organiser=organiser, can_change_teams=False)
    non_matching.members.add(user)
    TeamFactory(organiser=other).members.add(user)
    TeamFactory(organiser=organiser, can_change_teams=True)

    assert set(user_teams_in_organiser(user, organiser)) == {matching, non_matching}
    assert list(user_teams_in_organiser(user, organiser, can_change_teams=True)) == [
        matching
    ]
    assert not user_teams_in_organiser(UserFactory(), organiser)


def test_reviewer_team_queries_return_reviewer_teams_of_the_event_only():
    event = EventFactory()
    other_event = EventFactory(organiser=event.organiser)
    user = UserFactory()
    reviewer_team = TeamFactory(
        organiser=event.organiser, all_events=True, is_reviewer=True
    )
    reviewer_team.members.add(user)
    not_reviewer_team = TeamFactory(
        organiser=event.organiser, all_events=True, is_reviewer=False
    )
    not_reviewer_team.members.add(user)
    other_member_team = TeamFactory(
        organiser=event.organiser, all_events=True, is_reviewer=True
    )
    other_member_team.members.add(UserFactory())
    other_event_team = TeamFactory(organiser=event.organiser, is_reviewer=True)
    other_event_team.limit_events.add(other_event)
    other_event_team.members.add(user)

    assert set(event_reviewer_teams(event)) == {reviewer_team, other_member_team}
    assert list(user_reviewer_teams_in_event(user, event)) == [reviewer_team]
    assert not user_reviewer_teams_in_event(UserFactory(), event)


def test_speaker_access_administrator_sees_all_events_and_can_filter(event):
    user = UserFactory(is_administrator=True)
    same_org_event = EventFactory(organiser=event.organiser)
    foreign_event = EventFactory()

    result = speaker_access_events_for_user(user=user)

    assert set(result) == {event, same_org_event, foreign_event}
    assert set(result.filter(organiser=event.organiser)) == {event, same_org_event}


@pytest.mark.parametrize(
    ("team_kwargs", "limit", "expected"),
    (
        ({"can_change_submissions": True, "all_events": True}, None, "both"),
        ({"can_change_submissions": True, "all_events": False}, "event", "event"),
        ({"is_reviewer": True, "can_change_submissions": False}, None, "both"),
        (
            {"is_reviewer": True, "can_change_submissions": False, "all_events": False},
            None,
            "none",
        ),
        (
            {
                "is_reviewer": True,
                "can_change_submissions": False,
                "force_hide_speaker_names": True,
            },
            None,
            "none",
        ),
        ({"is_reviewer": True, "can_change_submissions": False}, "track", "none"),
    ),
    ids=(
        "submissions_all_events",
        "submissions_limited",
        "reviewer_all_events",
        "reviewer_no_events",
        "reviewer_names_hidden",
        "reviewer_track_limited",
    ),
)
def test_speaker_access_follows_team_permissions(event, team_kwargs, limit, expected):
    other_event = EventFactory(organiser=event.organiser)
    EventFactory()
    team = TeamFactory(organiser=event.organiser, **{"all_events": True, **team_kwargs})
    user = UserFactory()
    team.members.add(user)
    if limit == "event":
        team.limit_events.add(event)
    if limit == "track":
        team.limit_tracks.add(TrackFactory(event=event))
    expected_events = {"both": {event, other_event}, "event": {event}, "none": set()}

    result = speaker_access_events_for_user(user=user)

    assert set(result) == expected_events[expected]


def test_speaker_access_direct_access_and_permitted_reviewer_win_over_denied(event):
    other_event = EventFactory(organiser=event.organiser)
    third_event = EventFactory(organiser=event.organiser)
    submission_team = TeamFactory(
        organiser=event.organiser, can_change_submissions=True, all_events=False
    )
    submission_team.limit_events.add(event)
    denied_reviewer_team = TeamFactory(
        organiser=event.organiser,
        is_reviewer=True,
        can_change_submissions=False,
        all_events=True,
        force_hide_speaker_names=True,
    )
    permitted_reviewer_team = TeamFactory(
        organiser=event.organiser,
        is_reviewer=True,
        can_change_submissions=False,
        all_events=False,
        force_hide_speaker_names=False,
    )
    permitted_reviewer_team.limit_events.add(third_event)
    user = UserFactory()
    submission_team.members.add(user)
    denied_reviewer_team.members.add(user)
    permitted_reviewer_team.members.add(user)

    result = speaker_access_events_for_user(user=user)

    assert set(result) == {event, third_event}
    assert other_event not in result


def test_speaker_access_spans_organisers_with_membership_only(event):
    other_organiser = OrganiserFactory()
    other_event = EventFactory(organiser=other_organiser)
    EventFactory()
    here = TeamFactory(
        organiser=event.organiser, can_change_submissions=True, all_events=True
    )
    there = TeamFactory(
        organiser=other_organiser, can_change_submissions=True, all_events=True
    )
    user = UserFactory()
    here.members.add(user)
    there.members.add(user)

    result = speaker_access_events_for_user(user=user)

    assert set(result) == {event, other_event}
    assert set(result.filter(organiser=event.organiser)) == {event}
    assert set(speaker_access_events_for_user(user=UserFactory())) == set()


def test_active_reviewers_for_event_returns_distinct_reviewers_with_reviews():
    event = EventFactory()
    other_event = EventFactory(organiser=event.organiser)
    active = UserFactory()
    inactive = UserFactory()
    other_reviewer = UserFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(active, inactive)
    for _ in range(3):
        ReviewFactory(submission=SubmissionFactory(event=event), user=active)
    other_team = TeamFactory(organiser=event.organiser, is_reviewer=True)
    other_team.limit_events.add(other_event)
    other_team.members.add(other_reviewer)
    ReviewFactory(submission=SubmissionFactory(event=other_event), user=other_reviewer)

    assert list(active_reviewers_for_event(event)) == [active]
