# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.views.team import (
    TeamInviteCreateSerializer,
    TeamMemberRemoveSerializer,
    TeamViewSet,
)
from tests.factories import OrganiserFactory, TeamFactory
from tests.utils import make_api_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_team_viewset_get_queryset_returns_organiser_teams(django_assert_num_queries):
    organiser = OrganiserFactory()
    team = TeamFactory(organiser=organiser, all_events=True)
    TeamFactory()

    request = make_api_request(organiser=organiser)
    view = make_view(TeamViewSet, request)
    view.action = "list"

    teams = list(view.get_queryset())

    assert teams == [team]
    with django_assert_num_queries(0):
        list(teams[0].members.all())
        list(teams[0].invites.all())
        list(teams[0].limit_events.all())
        list(teams[0].limit_tracks.all())


@pytest.mark.parametrize(
    ("data", "errors"),
    (
        ({"email": "test@example.com"}, {}),
        ({"email": "not-an-email"}, {"email": ["Enter a valid email address."]}),
    ),
)
def test_team_invite_create_serializer(data, errors):
    serializer = TeamInviteCreateSerializer(data=data)

    assert serializer.is_valid() == (not errors)
    assert serializer.errors == errors


@pytest.mark.parametrize(
    ("data", "errors"),
    (({"user_code": "ABCDEF"}, {}), ({}, {"user_code": ["This field is required."]})),
)
def test_team_member_remove_serializer(data, errors):
    serializer = TeamMemberRemoveSerializer(data=data)

    assert serializer.is_valid() == (not errors)
    assert serializer.errors == errors
