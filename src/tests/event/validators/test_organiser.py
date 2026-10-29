# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.event.validators.organiser import check_access_permissions
from tests.factories import EventFactory, OrganiserFactory, TeamFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

ALL_PERMISSIONS = {
    "can_change_teams": True,
    "can_create_events": True,
    "can_change_organiser_settings": True,
    "can_change_event_settings": True,
    "all_events": True,
}


def test_check_access_permissions_requires_a_member_team_that_can_change_teams():
    organiser = OrganiserFactory()
    TeamFactory(
        organiser=organiser, can_change_teams=False, can_create_events=True
    ).members.add(UserFactory())
    empty_team = TeamFactory(organiser=organiser, can_change_teams=True)

    with pytest.raises(ValidationError):
        check_access_permissions(organiser)

    empty_team.members.add(UserFactory())

    assert [code for code, _msg in check_access_permissions(organiser)] == [
        "no_can_change_organiser_settings"
    ]
    with pytest.raises(ValidationError):
        check_access_permissions(organiser, exclude_team=empty_team)


@pytest.mark.parametrize(
    ("team_kwargs", "limit_to_event", "expected_codes"),
    (
        ({}, False, []),
        ({"all_events": False}, True, []),
        ({"can_create_events": False}, False, ["no_can_create_events"]),
        (
            {"can_change_organiser_settings": False},
            False,
            ["no_can_change_organiser_settings"],
        ),
        ({"can_change_event_settings": False}, False, ["no_can_change_event_settings"]),
    ),
    ids=(
        "all_permissions",
        "event_covered_by_limit_events",
        "missing_can_create_events",
        "missing_can_change_organiser_settings",
        "missing_can_change_event_settings",
    ),
)
def test_check_access_permissions_warns_about_missing_permissions(
    team_kwargs, limit_to_event, expected_codes
):
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    team = TeamFactory(organiser=organiser, **{**ALL_PERMISSIONS, **team_kwargs})
    team.members.add(UserFactory())
    if limit_to_event:
        team.limit_events.add(event)

    warnings = check_access_permissions(organiser)

    assert [code for code, _msg in warnings] == expected_codes


def test_check_access_permissions_raises_when_an_event_has_no_team_access():
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    safety = TeamFactory(
        organiser=organiser, **{**ALL_PERMISSIONS, "all_events": False}
    )
    safety.members.add(UserFactory())

    with pytest.raises(ValidationError) as excinfo:
        check_access_permissions(organiser)

    assert event.name in str(excinfo.value)

    coverage = TeamFactory(
        organiser=organiser,
        can_change_teams=True,
        can_change_event_settings=True,
        all_events=False,
    )
    coverage.members.add(UserFactory())
    coverage.limit_events.add(event)

    assert check_access_permissions(organiser) == []
    with pytest.raises(ValidationError) as excinfo:
        check_access_permissions(organiser, exclude_team=coverage)
    assert event.name in str(excinfo.value)


def test_check_access_permissions_exclude_team_passes_with_backup_team():
    organiser = OrganiserFactory()
    team = TeamFactory(organiser=organiser, **ALL_PERMISSIONS)
    team.members.add(UserFactory())
    backup = TeamFactory(organiser=organiser, **ALL_PERMISSIONS)
    backup.members.add(UserFactory())

    assert check_access_permissions(organiser, exclude_team=team) == []


@pytest.mark.parametrize("event_count", (1, 3))
def test_check_access_permissions_query_count_constant(
    event_count, django_assert_num_queries
):
    organiser = OrganiserFactory()
    team = TeamFactory(organiser=organiser, **ALL_PERMISSIONS)
    team.members.add(UserFactory())
    for _i in range(event_count):
        EventFactory(organiser=organiser)

    with django_assert_num_queries(3):
        warnings = check_access_permissions(organiser)

    assert warnings == []
