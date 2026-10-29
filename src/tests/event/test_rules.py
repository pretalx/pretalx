# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.contrib.auth.models import AnonymousUser

from pretalx.event.rules import (
    can_change_any_organiser_settings,
    can_change_event_settings,
    can_change_organiser_settings,
    can_change_teams,
    can_create_events,
    check_team_permission,
    has_any_organiser_permissions,
    has_any_permission,
    is_any_organiser,
    is_event_visible,
)
from tests.factories import EventFactory, OrganiserFactory, TeamFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(("is_public", "expected"), ((True, True), (False, False)))
def test_is_event_visible_returns_public_status(is_public, expected):
    event = EventFactory(is_public=is_public)
    user = UserFactory()
    assert is_event_visible(user, event) == expected


def test_is_event_visible_returns_falsy_when_event_is_none():
    assert not is_event_visible(None, None)


@pytest.mark.parametrize(
    ("predicate", "obj_kind"),
    (
        (check_team_permission, "event"),
        (can_change_teams, "event"),
        (can_change_organiser_settings, "organiser"),
        (has_any_organiser_permissions, "organiser"),
        (can_change_any_organiser_settings, None),
        (can_create_events, None),
        (is_any_organiser, None),
    ),
)
def test_predicates_return_true_for_administrator(predicate, obj_kind):
    user = UserFactory(is_administrator=True)
    obj = {"event": EventFactory, "organiser": OrganiserFactory, None: lambda: None}[
        obj_kind
    ]()
    args = ("can_change_event_settings",) if predicate is check_team_permission else ()

    assert predicate(user, obj, *args) is True


@pytest.mark.parametrize(("has_perm", "expected"), ((True, True), (False, False)))
def test_check_team_permission_follows_team_permission(has_perm, expected):
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    user = UserFactory()
    team = TeamFactory(
        organiser=organiser, all_events=True, can_change_event_settings=has_perm
    )
    team.members.add(user)

    assert check_team_permission(user, event, "can_change_event_settings") is expected
    assert can_change_event_settings(user, event) is expected


@pytest.mark.parametrize("user_val", (None, "anonymous"), ids=("none", "anonymous"))
def test_can_change_event_settings_returns_false_for_unauthenticated(user_val):
    event = EventFactory()
    user = AnonymousUser() if user_val == "anonymous" else None
    assert can_change_event_settings(user, event) is False


@pytest.mark.parametrize(
    "obj", (None, type("NoEvent", (), {})()), ids=("none", "no_event_attribute")
)
def test_can_change_event_settings_returns_false_without_event(obj):
    user = UserFactory()
    assert can_change_event_settings(user, obj) is False


@pytest.mark.parametrize(("has_perm", "expected"), ((True, True), (False, False)))
def test_can_change_teams_with_event_permission(has_perm, expected):
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    user = UserFactory()
    team = TeamFactory(organiser=organiser, all_events=True, can_change_teams=has_perm)
    team.members.add(user)

    assert can_change_teams(user, event) is expected


@pytest.mark.parametrize(("has_perm", "expected"), ((True, True), (False, False)))
def test_can_change_teams_organiser_fallback(has_perm, expected):
    organiser = OrganiserFactory()
    user = UserFactory()
    team = TeamFactory(organiser=organiser, can_change_teams=has_perm)
    team.members.add(user)

    assert can_change_teams(user, organiser) is expected


@pytest.mark.parametrize("user_val", (None, "anonymous"), ids=("none", "anonymous"))
def test_can_change_teams_returns_false_for_unauthenticated(user_val):
    user = AnonymousUser() if user_val == "anonymous" else None
    assert can_change_teams(user, object()) is False


@pytest.mark.parametrize(("has_perm", "expected"), ((True, True), (False, False)))
def test_can_change_organiser_settings_with_organiser_team(has_perm, expected):
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    user = UserFactory()
    team = TeamFactory(organiser=organiser, can_change_organiser_settings=has_perm)
    team.members.add(user)

    assert can_change_organiser_settings(user, organiser) is expected
    assert can_change_organiser_settings(user, event) is expected


@pytest.mark.parametrize(("has_team", "expected"), ((True, True), (False, False)))
def test_has_any_permission_and_organiser_permissions_follow_team_membership(
    has_team, expected
):
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    user = UserFactory()
    if has_team:
        team = TeamFactory(organiser=organiser, all_events=True)
        team.members.add(user)

    assert has_any_permission(user, event) is expected
    assert has_any_organiser_permissions(user, organiser) is expected
    assert has_any_organiser_permissions(user, event) is expected
    assert is_any_organiser(user, None) is expected


@pytest.mark.parametrize(("has_perm", "expected"), ((True, True), (False, False)))
def test_can_change_any_organiser_settings_with_team(has_perm, expected):
    user = UserFactory()
    team = TeamFactory(can_change_organiser_settings=has_perm)
    team.members.add(user)

    assert can_change_any_organiser_settings(user, None) is expected


@pytest.mark.parametrize(("has_perm", "expected"), ((True, True), (False, False)))
def test_can_create_events_with_team(has_perm, expected):
    user = UserFactory()
    team = TeamFactory(can_create_events=has_perm)
    team.members.add(user)

    assert can_create_events(user, None) is expected


def test_organiser_predicates_use_cached_teams(django_assert_num_queries):
    organiser = OrganiserFactory()
    user = UserFactory()
    team = TeamFactory(
        organiser=organiser,
        can_change_teams=True,
        can_change_organiser_settings=True,
        can_create_events=True,
    )
    team.members.add(user)

    assert is_any_organiser(user, None) is True
    with django_assert_num_queries(0):
        assert can_change_teams(user, organiser) is True
        assert can_change_organiser_settings(user, organiser) is True
        assert can_change_any_organiser_settings(user, None) is True
        assert can_create_events(user, None) is True
        assert has_any_organiser_permissions(user, organiser) is True
        assert is_any_organiser(user, None) is True
