# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.event.domain.queries.organiser import organisers_for_user
from tests.factories import EventFactory, OrganiserFactory, TeamFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_organisers_for_user_admin_sees_all():
    org1 = OrganiserFactory()
    org2 = OrganiserFactory()
    admin = UserFactory(is_administrator=True)

    result = organisers_for_user(admin)

    assert {o.pk for o in result} == {org1.pk, org2.pk}


def test_organisers_for_user_non_admin_sees_only_settings_teams():
    granted = OrganiserFactory()
    OrganiserFactory()  # no team membership
    other = OrganiserFactory()
    user = UserFactory()
    settings_team = TeamFactory(
        organiser=granted, can_change_organiser_settings=True, all_events=True
    )
    settings_team.members.add(user)
    plain_team = TeamFactory(
        organiser=other, can_change_organiser_settings=False, all_events=True
    )
    plain_team.members.add(user)

    result = organisers_for_user(user)

    assert list(result) == [granted]


def test_organisers_for_user_returns_empty_for_user_without_teams():
    OrganiserFactory()
    user = UserFactory()

    assert list(organisers_for_user(user)) == []


def test_organisers_for_user_annotates_event_and_team_counts():
    org = OrganiserFactory()
    EventFactory(organiser=org)
    EventFactory(organiser=org)
    TeamFactory(organiser=org)
    TeamFactory(organiser=org)
    admin = UserFactory(is_administrator=True)

    result = organisers_for_user(admin).get(pk=org.pk)

    assert result.event_count == 2
    assert result.team_count == 2
