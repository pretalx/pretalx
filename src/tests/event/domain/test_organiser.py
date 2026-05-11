# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.common.models import ActivityLog
from pretalx.event.domain.organiser import create_organiser_with_team, shred_organiser
from pretalx.event.models import Event, Organiser, Team
from tests.factories import EventFactory, OrganiserFactory, UserFactory

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


def test_shred_organiser_deletes_organiser():
    organiser = OrganiserFactory()
    pk = organiser.pk

    shred_organiser(organiser)

    assert not Organiser.objects.filter(pk=pk).exists()


def test_shred_organiser_deletes_related_events():
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    event_pk = event.pk

    shred_organiser(organiser)

    assert not Event.objects.filter(pk=event_pk).exists()


def test_shred_organiser_logs_activity():
    organiser = OrganiserFactory()
    slug = organiser.slug
    user = UserFactory()

    shred_organiser(organiser, person=user)

    log = ActivityLog.objects.filter(action_type="pretalx.organiser.delete").first()
    assert log is not None
    assert log.person == user
    assert log.data["slug"] == slug
