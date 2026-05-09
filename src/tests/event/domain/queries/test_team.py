# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.event.domain.queries.team import (
    event_reviewer_teams,
    event_reviewers,
    user_reviewer_teams_in_event,
    user_teams_in_organiser,
)
from tests.factories import EventFactory, OrganiserFactory, TeamFactory, UserFactory

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


def test_event_reviewers_returns_members_of_reviewer_teams_only():
    event = EventFactory()
    reviewer = UserFactory()
    non_reviewer = UserFactory()
    reviewer_team = TeamFactory(
        organiser=event.organiser, all_events=True, is_reviewer=True
    )
    reviewer_team.members.add(reviewer)
    plain_team = TeamFactory(
        organiser=event.organiser, all_events=True, is_reviewer=False
    )
    plain_team.members.add(non_reviewer)

    assert list(event_reviewers(event)) == [reviewer]


def test_event_reviewers_deduplicates_across_multiple_reviewer_teams():
    event = EventFactory()
    user = UserFactory()
    first = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    second = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    first.members.add(user)
    second.members.add(user)

    assert list(event_reviewers(event)) == [user]


def test_event_reviewers_excludes_other_events_reviewers():
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    other_event = EventFactory(organiser=organiser)
    other_team = TeamFactory(organiser=organiser, is_reviewer=True)
    other_team.limit_events.add(other_event)
    other_team.members.add(UserFactory())

    assert not event_reviewers(event).exists()


def test_event_reviewers_matches_event_reviewers_property():
    event = EventFactory()
    user = UserFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(user)

    assert list(event_reviewers(event)) == list(event.reviewers)
