# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.event.validators.organiser import check_access_permissions
from tests.factories import EventFactory, OrganiserFactory, TeamFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_check_access_permissions_raises_when_no_team_can_change_teams():
    """Must have at least one team with can_change_teams and members."""
    organiser = OrganiserFactory()
    user = UserFactory()
    team = TeamFactory(
        organiser=organiser, can_change_teams=False, can_create_events=True
    )
    team.members.add(user)

    with pytest.raises(ValidationError):
        check_access_permissions(organiser)


@pytest.mark.parametrize(
    ("missing_perm", "expected_code"),
    (
        ("can_create_events", "no_can_create_events"),
        ("can_change_organiser_settings", "no_can_change_organiser_settings"),
    ),
)
def test_check_access_permissions_warns_when_organiser_level_permission_missing(
    missing_perm, expected_code
):
    organiser = OrganiserFactory()
    user = UserFactory()
    kwargs = {
        "organiser": organiser,
        "can_change_teams": True,
        "can_create_events": True,
        "can_change_organiser_settings": True,
    }
    kwargs[missing_perm] = False
    team = TeamFactory(**kwargs)
    team.members.add(user)

    warnings = check_access_permissions(organiser)

    codes = [code for code, _msg in warnings]
    assert codes == [expected_code]


def test_check_access_permissions_raises_when_event_has_no_team_access():
    """Every event must be covered by at least one team with members."""
    organiser = OrganiserFactory()
    user = UserFactory()
    team = TeamFactory(
        organiser=organiser,
        can_change_teams=True,
        can_create_events=True,
        can_change_organiser_settings=True,
        all_events=False,
    )
    team.members.add(user)
    EventFactory(organiser=organiser)

    with pytest.raises(ValidationError):
        check_access_permissions(organiser)


def test_check_access_permissions_warns_when_event_team_lacks_change_settings():
    organiser = OrganiserFactory()
    user = UserFactory()
    team = TeamFactory(
        organiser=organiser,
        can_change_teams=True,
        can_create_events=True,
        can_change_organiser_settings=True,
        can_change_event_settings=False,
        all_events=True,
    )
    team.members.add(user)
    EventFactory(organiser=organiser)

    warnings = check_access_permissions(organiser)

    codes = [code for code, _msg in warnings]
    assert codes == ["no_can_change_event_settings"]


def test_check_access_permissions_no_warnings_when_all_permissions_present():
    organiser = OrganiserFactory()
    user = UserFactory()
    team = TeamFactory(
        organiser=organiser,
        can_change_teams=True,
        can_create_events=True,
        can_change_organiser_settings=True,
        can_change_event_settings=True,
        all_events=True,
    )
    team.members.add(user)
    EventFactory(organiser=organiser)

    warnings = check_access_permissions(organiser)

    assert warnings == []


def test_check_access_permissions_ignores_teams_without_members():
    """Teams without members don't count for permission checks."""
    organiser = OrganiserFactory()
    TeamFactory(organiser=organiser, can_change_teams=True)

    with pytest.raises(ValidationError):
        check_access_permissions(organiser)


def test_check_access_permissions_event_covered_by_limit_events():
    """An event is covered if a team has it in limit_events (not just all_events)."""
    organiser = OrganiserFactory()
    user = UserFactory()
    event = EventFactory(organiser=organiser)
    team = TeamFactory(
        organiser=organiser,
        can_change_teams=True,
        can_create_events=True,
        can_change_organiser_settings=True,
        can_change_event_settings=True,
        all_events=False,
    )
    team.members.add(user)
    team.limit_events.add(event)

    warnings = check_access_permissions(organiser)

    assert warnings == []


def test_check_access_permissions_exclude_team_raises_when_last_change_teams():
    organiser = OrganiserFactory()
    team = TeamFactory(organiser=organiser, can_change_teams=True)
    team.members.add(UserFactory())

    with pytest.raises(ValidationError):
        check_access_permissions(organiser, exclude_team=team)


def test_check_access_permissions_exclude_team_raises_when_event_uncovered():
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    safety = TeamFactory(organiser=organiser, can_change_teams=True, all_events=False)
    safety.members.add(UserFactory())
    coverage = TeamFactory(organiser=organiser, can_change_teams=True, all_events=False)
    coverage.members.add(UserFactory())
    coverage.limit_events.add(event)

    with pytest.raises(ValidationError) as excinfo:
        check_access_permissions(organiser, exclude_team=coverage)

    assert event.name in str(excinfo.value)


def test_check_access_permissions_exclude_team_passes_with_backup_team():
    organiser = OrganiserFactory()
    perms = {
        "can_change_teams": True,
        "can_create_events": True,
        "can_change_organiser_settings": True,
        "can_change_event_settings": True,
        "all_events": True,
    }
    team = TeamFactory(organiser=organiser, **perms)
    team.members.add(UserFactory())
    backup = TeamFactory(organiser=organiser, **perms)
    backup.members.add(UserFactory())

    assert check_access_permissions(organiser, exclude_team=team) == []


@pytest.mark.parametrize("event_count", (1, 3))
def test_check_access_permissions_query_count_constant(
    event_count, django_assert_num_queries
):
    organiser = OrganiserFactory()
    team = TeamFactory(
        organiser=organiser,
        can_change_teams=True,
        can_create_events=True,
        can_change_organiser_settings=True,
        can_change_event_settings=True,
        all_events=True,
    )
    team.members.add(UserFactory())
    for _i in range(event_count):
        EventFactory(organiser=organiser)

    with django_assert_num_queries(3):
        warnings = check_access_permissions(organiser)

    assert warnings == []
