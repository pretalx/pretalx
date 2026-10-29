# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.common.models import ActivityLog
from pretalx.event.domain.organiser import create_organiser_with_team, shred_organiser
from pretalx.event.models import Event, Organiser, Team
from tests.factories import EventFactory, OrganiserFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_create_organiser_with_team_creates_organiser_and_owning_team():
    user1 = UserFactory()
    user2 = UserFactory()

    organiser, team = create_organiser_with_team(
        name="TestOrg", slug="MixedCase", users=[user1, user2]
    )

    organiser = Organiser.objects.get(pk=organiser.pk)
    team = Team.objects.select_related("organiser").get(pk=team.pk)
    assert organiser.name == "TestOrg"
    assert organiser.slug == "mixedcase"
    assert team.organiser == organiser
    assert team.name == "Team TestOrg"
    assert team.can_create_events is True
    assert team.can_change_teams is True
    assert team.can_change_organiser_settings is True
    assert set(team.members.all()) == {user1, user2}
    assert list(user1.teams.all()) == [team]


def test_shred_organiser_deletes_organiser_with_events_and_logs():
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    user = UserFactory()
    slug = organiser.slug
    pk = organiser.pk

    shred_organiser(organiser, person=user)

    assert not Organiser.objects.filter(pk=pk).exists()
    assert not Event.objects.filter(pk=event.pk).exists()
    log = (
        ActivityLog.objects.select_related("person")
        .filter(action_type="pretalx.organiser.delete")
        .get()
    )
    assert log.person == user
    assert log.data["slug"] == slug
