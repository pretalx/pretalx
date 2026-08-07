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


def test_user_teams_in_organiser_returns_user_teams_only_for_that_organiser():
    organiser = OrganiserFactory()
    other = OrganiserFactory()
    user = UserFactory()
    in_team = TeamFactory(organiser=organiser)
    in_team.members.add(user)
    other_team = TeamFactory(organiser=other)
    other_team.members.add(user)

    result = list(user_teams_in_organiser(user, organiser))

    assert result == [in_team]


def test_user_teams_in_organiser_filters_by_extra_kwargs():
    organiser = OrganiserFactory()
    user = UserFactory()
    matching = TeamFactory(organiser=organiser, can_change_teams=True)
    matching.members.add(user)
    non_matching = TeamFactory(organiser=organiser, can_change_teams=False)
    non_matching.members.add(user)

    result = list(user_teams_in_organiser(user, organiser, can_change_teams=True))

    assert result == [matching]


def test_user_teams_in_organiser_returns_empty_when_user_has_no_team_there():
    organiser = OrganiserFactory()
    user = UserFactory()

    assert not user_teams_in_organiser(user, organiser).exists()


def test_event_reviewer_teams_returns_reviewer_teams_of_the_event():
    event = EventFactory()
    reviewer_team = TeamFactory(
        organiser=event.organiser, all_events=True, is_reviewer=True
    )
    TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=False)

    other_event = EventFactory(organiser=event.organiser)
    other_team = TeamFactory(organiser=event.organiser, is_reviewer=True)
    other_team.limit_events.add(other_event)

    result = list(event_reviewer_teams(event))

    assert result == [reviewer_team]


def test_user_reviewer_teams_in_event_returns_only_user_reviewer_teams():
    event = EventFactory()
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

    result = list(user_reviewer_teams_in_event(user, event))

    assert result == [reviewer_team]


def test_user_reviewer_teams_in_event_excludes_other_events():
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    other_event = EventFactory(organiser=organiser)
    user = UserFactory()
    other_event_team = TeamFactory(organiser=organiser, is_reviewer=True)
    other_event_team.limit_events.add(other_event)
    other_event_team.members.add(user)

    assert not user_reviewer_teams_in_event(user, event).exists()


def test_speaker_access_administrator_filtered_to_organiser(event):
    user = UserFactory(is_administrator=True)
    same_org_event = EventFactory(organiser=event.organiser)
    foreign_event = EventFactory()  # different organiser

    result = speaker_access_events_for_user(user=user).filter(organiser=event.organiser)

    assert set(result) == {event, same_org_event}
    assert foreign_event not in result


def test_speaker_access_for_user_administrator_sees_events_without_team(event):
    user = UserFactory(is_administrator=True)
    foreign_event = EventFactory()  # admin has no team here

    result = speaker_access_events_for_user(user=user)

    assert {event, foreign_event}.issubset(set(result))


def test_speaker_access_can_change_submissions_all_events(event):
    other_event = EventFactory(organiser=event.organiser)
    team = TeamFactory(
        organiser=event.organiser, can_change_submissions=True, all_events=True
    )
    user = UserFactory()
    team.members.add(user)

    result = speaker_access_events_for_user(user=user)

    assert set(result) == {event, other_event}


def test_speaker_access_can_change_submissions_limited(event):
    other_event = EventFactory(organiser=event.organiser)
    team = TeamFactory(
        organiser=event.organiser, can_change_submissions=True, all_events=False
    )
    team.limit_events.add(event)
    user = UserFactory()
    team.members.add(user)

    result = speaker_access_events_for_user(user=user)

    assert set(result) == {event}
    assert other_event not in result


def test_speaker_access_reviewer_team_grants_when_perm_holds(event):
    other_event = EventFactory(organiser=event.organiser)
    team_with_perm = TeamFactory(
        organiser=event.organiser,
        is_reviewer=True,
        can_change_submissions=False,
        all_events=False,
        force_hide_speaker_names=False,
    )
    team_with_perm.limit_events.add(event)
    team_no_perm = TeamFactory(
        organiser=event.organiser,
        is_reviewer=True,
        can_change_submissions=False,
        all_events=False,
        force_hide_speaker_names=True,
    )
    team_no_perm.limit_events.add(other_event)
    user = UserFactory()
    team_with_perm.members.add(user)
    team_no_perm.members.add(user)

    result = speaker_access_events_for_user(user=user)

    assert set(result) == {event}


def test_speaker_access_reviewer_no_events(event):
    team = TeamFactory(
        organiser=event.organiser,
        is_reviewer=True,
        can_change_submissions=False,
        all_events=False,
    )
    user = UserFactory()
    team.members.add(user)

    result = speaker_access_events_for_user(user=user)

    assert set(result) == set()


def test_speaker_access_direct_access_wins_over_denied_reviewer(event):
    submission_team = TeamFactory(
        organiser=event.organiser, can_change_submissions=True, all_events=False
    )
    submission_team.limit_events.add(event)
    reviewer_team = TeamFactory(
        organiser=event.organiser,
        is_reviewer=True,
        can_change_submissions=False,
        all_events=True,
        force_hide_speaker_names=True,
    )
    user = UserFactory()
    submission_team.members.add(user)
    reviewer_team.members.add(user)

    result = speaker_access_events_for_user(user=user)

    assert set(result) == {event}


def test_speaker_access_reviewer_denied_excluded(event):
    team = TeamFactory(
        organiser=event.organiser,
        is_reviewer=True,
        can_change_submissions=False,
        all_events=True,
        force_hide_speaker_names=True,
    )
    user = UserFactory()
    team.members.add(user)

    result = speaker_access_events_for_user(user=user)

    assert set(result) == set()


def test_speaker_access_track_limited_reviewer_skipped(event):
    track = TrackFactory(event=event)
    team = TeamFactory(
        organiser=event.organiser,
        is_reviewer=True,
        can_change_submissions=False,
        all_events=True,
    )
    team.limit_tracks.add(track)
    user = UserFactory()
    team.members.add(user)

    result = speaker_access_events_for_user(user=user)

    assert set(result) == set()


def test_speaker_access_reviewer_all_events_with_permission(event):
    other_event = EventFactory(organiser=event.organiser)
    team = TeamFactory(
        organiser=event.organiser,
        is_reviewer=True,
        can_change_submissions=False,
        all_events=True,
    )
    user = UserFactory()
    team.members.add(user)

    result = speaker_access_events_for_user(user=user)

    assert set(result) == {event, other_event}


def test_speaker_access_organiser_filter_excludes_foreign_organiser_team(event):
    other_organiser = OrganiserFactory()
    EventFactory(organiser=other_organiser)
    foreign_team = TeamFactory(
        organiser=other_organiser, can_change_submissions=True, all_events=True
    )
    user = UserFactory()
    foreign_team.members.add(user)

    result = speaker_access_events_for_user(user=user).filter(organiser=event.organiser)

    assert set(result) == set()


def test_speaker_access_for_user_spans_multiple_organisers(event):
    other_organiser = OrganiserFactory()
    other_event = EventFactory(organiser=other_organiser)
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


def test_speaker_access_for_user_excludes_organisers_without_membership(event):
    foreign_event = EventFactory()  # different organiser, no membership
    sibling_event = EventFactory(organiser=event.organiser)  # same organiser, but…
    team = TeamFactory(
        organiser=event.organiser, can_change_submissions=True, all_events=False
    )
    team.limit_events.add(event)  # …team only grants `event`
    user = UserFactory()
    team.members.add(user)

    result = speaker_access_events_for_user(user=user)

    assert set(result) == {event}
    assert foreign_event not in result
    assert sibling_event not in result


def test_speaker_access_for_user_no_membership_returns_nothing():
    EventFactory()
    EventFactory()
    user = UserFactory()

    result = speaker_access_events_for_user(user=user)

    assert set(result) == set()


def test_active_reviewers_for_event_returns_only_reviewers_with_reviews():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    active = UserFactory()
    inactive = UserFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(active)
    team.members.add(inactive)
    ReviewFactory(submission=submission, user=active)

    assert list(active_reviewers_for_event(event)) == [active]


def test_active_reviewers_for_event_deduplicates_across_multiple_reviews():
    event = EventFactory()
    user = UserFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(user)
    for _ in range(3):
        ReviewFactory(submission=SubmissionFactory(event=event), user=user)

    assert list(active_reviewers_for_event(event)) == [user]


def test_active_reviewers_for_event_excludes_reviewers_of_other_events():
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    other_event = EventFactory(organiser=organiser)
    user = UserFactory()
    other_team = TeamFactory(organiser=organiser, is_reviewer=True)
    other_team.limit_events.add(other_event)
    other_team.members.add(user)
    ReviewFactory(submission=SubmissionFactory(event=other_event), user=user)

    assert list(active_reviewers_for_event(event)) == []
