import datetime as dt

import pytest
from django.contrib.auth.models import AnonymousUser
from django_scopes import scopes_disabled

from pretalx.event.models import Event
from pretalx.event.rules import (
    can_change_any_organiser_settings,
    can_change_event_settings,
    can_change_organiser_settings,
    can_change_teams,
    can_create_events,
    check_team_permission,
    get_events_for_user,
    has_any_organiser_permissions,
    has_any_permission,
    is_any_organiser,
    is_event_visible,
)
from tests.factories import EventFactory, OrganiserFactory, TeamFactory, UserFactory

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(("is_public", "expected"), ((True, True), (False, False)))
@pytest.mark.django_db
def test_is_event_visible_returns_public_status(is_public, expected):
    event = EventFactory(is_public=is_public)
    user = UserFactory()
    assert is_event_visible(user, event) == expected


def test_is_event_visible_returns_falsy_when_event_is_none():
    assert not is_event_visible(None, None)


@pytest.mark.django_db
def test_get_events_for_user_anonymous_returns_only_public_events():
    public_event = EventFactory(is_public=True)
    EventFactory(is_public=False)
    user = AnonymousUser()

    with scopes_disabled():
        result = list(get_events_for_user(user))

    assert result == [public_event]


@pytest.mark.django_db
def test_get_events_for_user_authenticated_returns_public_and_permitted():
    organiser = OrganiserFactory()
    public_event = EventFactory(is_public=True, organiser=organiser)
    private_event = EventFactory(is_public=False, organiser=organiser)
    EventFactory(is_public=False)  # no access
    user = UserFactory()
    team = TeamFactory(organiser=organiser, all_events=True)
    team.members.add(user)

    with scopes_disabled():
        result = set(get_events_for_user(user))

    assert result == {public_event, private_event}


@pytest.mark.django_db
def test_get_events_for_user_uses_provided_queryset():
    organiser = OrganiserFactory()
    EventFactory(is_public=True, organiser=organiser)
    other_event = EventFactory(is_public=True)
    user = AnonymousUser()

    with scopes_disabled():
        queryset = Event.objects.filter(organiser=other_event.organiser)
        result = list(get_events_for_user(user, queryset=queryset))

    assert result == [other_event]


@pytest.mark.django_db
def test_get_events_for_user_orders_by_date_from_descending():
    """Events are returned newest first."""
    e_old = EventFactory(is_public=True, date_from=dt.date(2020, 1, 1))
    e_new = EventFactory(is_public=True, date_from=dt.date(2025, 6, 1))
    user = AnonymousUser()

    with scopes_disabled():
        result = list(get_events_for_user(user))

    assert result == [e_new, e_old]


@pytest.mark.django_db
def test_check_team_permission_returns_true_for_administrator():
    event = EventFactory()
    user = UserFactory(is_administrator=True)
    assert check_team_permission(user, event, "can_change_event_settings") is True


@pytest.mark.django_db
def test_check_team_permission_returns_true_when_user_has_permission():
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    user = UserFactory()
    team = TeamFactory(
        organiser=organiser, all_events=True, can_change_event_settings=True
    )
    team.members.add(user)

    assert check_team_permission(user, event, "can_change_event_settings") is True


@pytest.mark.django_db
def test_check_team_permission_returns_false_when_user_lacks_permission():
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    user = UserFactory()
    team = TeamFactory(
        organiser=organiser, all_events=True, can_change_event_settings=False
    )
    team.members.add(user)

    assert check_team_permission(user, event, "can_change_event_settings") is False


@pytest.mark.django_db
def test_can_change_event_settings_returns_true_with_permission():
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    user = UserFactory()
    team = TeamFactory(
        organiser=organiser, all_events=True, can_change_event_settings=True
    )
    team.members.add(user)

    assert can_change_event_settings(user, event) is True


@pytest.mark.parametrize("user_val", (None, "anonymous"), ids=("none", "anonymous"))
@pytest.mark.django_db
def test_can_change_event_settings_returns_false_for_unauthenticated(user_val):
    event = EventFactory()
    user = AnonymousUser() if user_val == "anonymous" else None
    assert can_change_event_settings(user, event) is False


def test_can_change_event_settings_returns_false_when_obj_is_none():
    user = object()  # any non-None user
    assert can_change_event_settings(user, None) is False


@pytest.mark.django_db
def test_can_change_event_settings_returns_false_when_obj_has_no_event():
    """Objects without an event attribute should not grant permission."""
    user = UserFactory()

    class NoEvent:
        pass

    assert can_change_event_settings(user, NoEvent()) is False


@pytest.mark.django_db
def test_can_change_teams_returns_true_for_administrator():
    event = EventFactory()
    user = UserFactory(is_administrator=True)
    assert can_change_teams(user, event) is True


@pytest.mark.parametrize(("has_perm", "expected"), ((True, True), (False, False)))
@pytest.mark.django_db
def test_can_change_teams_with_event_permission(has_perm, expected):
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    user = UserFactory()
    team = TeamFactory(organiser=organiser, all_events=True, can_change_teams=has_perm)
    team.members.add(user)

    assert can_change_teams(user, event) is expected


@pytest.mark.parametrize(("has_perm", "expected"), ((True, True), (False, False)))
@pytest.mark.django_db
def test_can_change_teams_organiser_fallback(has_perm, expected):
    """When obj has no event attribute, checks teams via obj.organiser."""
    organiser = OrganiserFactory()
    user = UserFactory()
    team = TeamFactory(organiser=organiser, can_change_teams=has_perm)
    team.members.add(user)

    assert can_change_teams(user, organiser) is expected


@pytest.mark.parametrize("user_val", (None, "anonymous"), ids=("none", "anonymous"))
def test_can_change_teams_returns_false_for_unauthenticated(user_val):
    user = AnonymousUser() if user_val == "anonymous" else None
    assert can_change_teams(user, object()) is False


@pytest.mark.django_db
def test_can_change_organiser_settings_returns_true_for_administrator():
    organiser = OrganiserFactory()
    user = UserFactory(is_administrator=True)
    assert can_change_organiser_settings(user, organiser) is True


@pytest.mark.parametrize(("has_perm", "expected"), ((True, True), (False, False)))
@pytest.mark.django_db
def test_can_change_organiser_settings_with_organiser_team(has_perm, expected):
    organiser = OrganiserFactory()
    user = UserFactory()
    team = TeamFactory(organiser=organiser, can_change_organiser_settings=has_perm)
    team.members.add(user)

    assert can_change_organiser_settings(user, organiser) is expected


@pytest.mark.django_db
def test_can_change_organiser_settings_uses_event_organiser_when_obj_has_event():
    """When obj has an event attribute, the organiser is looked up via event."""
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    user = UserFactory()
    team = TeamFactory(organiser=organiser, can_change_organiser_settings=True)
    team.members.add(user)

    assert can_change_organiser_settings(user, event) is True


@pytest.mark.django_db
def test_has_any_permission_returns_true_when_user_has_permissions():
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    user = UserFactory()
    team = TeamFactory(organiser=organiser, all_events=True)
    team.members.add(user)

    assert has_any_permission(user, event) is True


@pytest.mark.django_db
def test_has_any_permission_returns_false_when_user_has_no_permissions():
    event = EventFactory()
    user = UserFactory()

    assert has_any_permission(user, event) is False


@pytest.mark.django_db
def test_has_any_organiser_permissions_returns_true_for_administrator():
    organiser = OrganiserFactory()
    user = UserFactory(is_administrator=True)
    assert has_any_organiser_permissions(user, organiser) is True


@pytest.mark.parametrize(("has_team", "expected"), ((True, True), (False, False)))
@pytest.mark.django_db
def test_has_any_organiser_permissions_with_team(has_team, expected):
    organiser = OrganiserFactory()
    user = UserFactory()
    if has_team:
        team = TeamFactory(organiser=organiser)
        team.members.add(user)

    assert has_any_organiser_permissions(user, organiser) is expected


@pytest.mark.django_db
def test_has_any_organiser_permissions_uses_obj_organiser_attribute():
    """When obj has an organiser attribute, that is used instead of obj itself."""
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    user = UserFactory()
    team = TeamFactory(organiser=organiser)
    team.members.add(user)

    assert has_any_organiser_permissions(user, event) is True


@pytest.mark.django_db
def test_can_change_any_organiser_settings_returns_true_for_administrator():
    user = UserFactory(is_administrator=True)
    assert can_change_any_organiser_settings(user, None) is True


@pytest.mark.parametrize(("has_perm", "expected"), ((True, True), (False, False)))
@pytest.mark.django_db
def test_can_change_any_organiser_settings_with_team(has_perm, expected):
    user = UserFactory()
    team = TeamFactory(can_change_organiser_settings=has_perm)
    team.members.add(user)

    assert can_change_any_organiser_settings(user, None) is expected


@pytest.mark.django_db
def test_can_create_events_returns_true_for_administrator():
    user = UserFactory(is_administrator=True)
    assert can_create_events(user, None) is True


@pytest.mark.parametrize(("has_perm", "expected"), ((True, True), (False, False)))
@pytest.mark.django_db
def test_can_create_events_with_team(has_perm, expected):
    user = UserFactory()
    team = TeamFactory(can_create_events=has_perm)
    team.members.add(user)

    assert can_create_events(user, None) is expected


@pytest.mark.django_db
def test_is_any_organiser_returns_true_for_administrator():
    user = UserFactory(is_administrator=True)
    assert is_any_organiser(user, None) is True


@pytest.mark.django_db
def test_is_any_organiser_returns_true_when_user_has_teams():
    user = UserFactory()
    team = TeamFactory()
    team.members.add(user)

    assert is_any_organiser(user, None) is True


@pytest.mark.django_db
def test_is_any_organiser_returns_false_when_user_has_no_teams():
    user = UserFactory()
    assert is_any_organiser(user, None) is False
