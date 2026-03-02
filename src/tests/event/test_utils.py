# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.event.models import Organiser, Team
from pretalx.event.utils import create_organiser_with_team
from tests.factories import UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_create_organiser_with_team_creates_organiser_and_team():
    user = UserFactory()

    organiser, team = create_organiser_with_team(
        name="TestOrg", slug="testorg", users=[user]
    )

    assert organiser.name == "TestOrg"
    assert organiser.slug == "testorg"
    assert Organiser.objects.filter(pk=organiser.pk).exists()
    assert Team.objects.filter(pk=team.pk).exists()


def test_create_organiser_with_team_sets_team_permissions():
    user = UserFactory()

    _, team = create_organiser_with_team(name="Org", slug="org", users=[user])

    assert team.can_create_events is True
    assert team.can_change_teams is True
    assert team.can_change_organiser_settings is True


def test_create_organiser_with_team_links_team_to_organiser():
    user = UserFactory()

    organiser, team = create_organiser_with_team(name="Org", slug="org", users=[user])

    assert team.organiser == organiser


def test_create_organiser_with_team_names_team_after_organiser():
    user = UserFactory()

    _, team = create_organiser_with_team(name="MyOrg", slug="myorg", users=[user])

    assert team.name == "Team MyOrg"


def test_create_organiser_with_team_adds_members():
    user1 = UserFactory()
    user2 = UserFactory()

    _, team = create_organiser_with_team(name="Org", slug="org", users=[user1, user2])

    assert set(team.members.all()) == {user1, user2}


def test_create_organiser_with_team_user_can_access_team():
    user = UserFactory()

    organiser, _ = create_organiser_with_team(name="Org", slug="org", users=[user])

    assert user.teams.count() == 1
    assert user.teams.get().organiser == organiser
