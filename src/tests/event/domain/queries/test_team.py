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
    """An administrator's queryset filtered by organiser returns exactly that
    organiser's events, not events from a different organiser."""
    user = UserFactory(is_administrator=True)
    same_org_event = EventFactory(organiser=event.organiser)
    foreign_event = EventFactory()  # different organiser

    result = speaker_access_events_for_user(user=user).filter(organiser=event.organiser)

    assert set(result) == {event, same_org_event}
    assert foreign_event not in result


def test_speaker_access_for_user_administrator_sees_events_without_team(event):
    """The administrator branch must return events from organisers the user has
    no team on at all — that's what makes the admin path different from the
    team-walking path."""
    user = UserFactory(is_administrator=True)
    foreign_event = EventFactory()  # admin has no team here

    result = speaker_access_events_for_user(user=user)

    assert {event, foreign_event}.issubset(set(result))


def test_speaker_access_can_change_submissions_all_events(event):
    """A can_change_submissions+all_events team grants every event of that
    organiser."""
    other_event = EventFactory(organiser=event.organiser)
    team = TeamFactory(
        organiser=event.organiser, can_change_submissions=True, all_events=True
    )
    user = UserFactory()
    team.members.add(user)

    result = speaker_access_events_for_user(user=user)

    assert set(result) == {event, other_event}


def test_speaker_access_can_change_submissions_limited(event):
    """can_change_submissions with limit_events grants only the listed events,
    even when a sibling event exists on the same organiser."""
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
    """A reviewer team without the speakerprofile permission must NOT grant
    access; flipping the relevant flag (force_hide_speaker_names) is what
    decides inclusion."""
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
    """A reviewer team with all_events=False and no limit_events grants
    nothing."""
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
    """When an event is granted by a can_change_submissions team, a parallel
    reviewer team that would deny it (force_hide_speaker_names) must not strip
    it. This pins the precedence rule and the underlying skip-already-granted
    behaviour."""
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
    """A reviewer team without granted speakerprofile permission contributes
    nothing on its own."""
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
    """Reviewer teams limited to specific tracks contribute nothing — even
    when they would otherwise grant access — because we do not yet filter
    speakers by track."""
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
    """A reviewer team with all_events=True and the speakerprofile permission
    grants the whole organiser's events."""
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
    """When the caller chains ``.filter(organiser=...)`` (as the organiser
    speaker views do), a team on a different organiser must not leak events
    into the result."""
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
    """The cross-organiser variant unions across every organiser the user has
    team membership on."""
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
    """An event on an organiser the user has no team on must not appear, even
    when the user has membership elsewhere."""
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
    """A user without any team membership gets an empty queryset, never the
    full Event table."""
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
    """A reviewer that submitted several reviews appears only once."""
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
