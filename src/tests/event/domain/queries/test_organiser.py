# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.event.domain.queries.organiser import organisers_for_user
from tests.factories import OrganiserFactory, TeamFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_organisers_for_user_admin_sees_all():
    org1 = OrganiserFactory()
    org2 = OrganiserFactory()
    admin = UserFactory(is_administrator=True)

    result = organisers_for_user(admin)

    assert set(result) == {org1, org2}


def test_organisers_for_user_filters_by_team_permissions():
    settings_org = OrganiserFactory()
    creator_org = OrganiserFactory()
    plain_org = OrganiserFactory()
    OrganiserFactory()  # no team membership
    user = UserFactory()
    TeamFactory(
        organiser=settings_org, can_change_organiser_settings=True, all_events=True
    ).members.add(user)
    TeamFactory(
        organiser=creator_org, can_create_events=True, all_events=True
    ).members.add(user)
    TeamFactory(
        organiser=plain_org, can_change_organiser_settings=False, all_events=True
    ).members.add(user)

    assert list(organisers_for_user(user)) == [settings_org]
    assert list(organisers_for_user(user, {"can_create_events": True})) == [creator_org]
    assert list(organisers_for_user(UserFactory())) == []
