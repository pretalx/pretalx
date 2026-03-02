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
def test_team_viewset_get_queryset_returns_organiser_teams():
    organiser = OrganiserFactory()
    team = TeamFactory(organiser=organiser, all_events=True)
    TeamFactory()  # different organiser's team

    request = make_api_request(organiser=organiser)
    view = make_view(TeamViewSet, request)
    view.action = "list"

    qs = list(view.get_queryset())

    assert qs == [team]


@pytest.mark.django_db
def test_team_viewset_get_queryset_prefetches_related(django_assert_num_queries):
    organiser = OrganiserFactory()
    TeamFactory(organiser=organiser, all_events=True)

    request = make_api_request(organiser=organiser)
    view = make_view(TeamViewSet, request)
    view.action = "list"

    teams = list(view.get_queryset())

    with django_assert_num_queries(0):
        list(teams[0].members.all())
        list(teams[0].invites.all())
        list(teams[0].limit_events.all())
        list(teams[0].limit_tracks.all())


def test_team_invite_create_serializer_validates_email():
    serializer = TeamInviteCreateSerializer(data={"email": "test@example.com"})

    assert serializer.is_valid()
    assert serializer.validated_data["email"] == "test@example.com"


def test_team_invite_create_serializer_rejects_invalid_email():
    serializer = TeamInviteCreateSerializer(data={"email": "not-an-email"})

    assert not serializer.is_valid()
    assert "email" in serializer.errors


def test_team_member_remove_serializer_validates_user_code():
    serializer = TeamMemberRemoveSerializer(data={"user_code": "ABCDEF"})

    assert serializer.is_valid()
    assert serializer.validated_data["user_code"] == "ABCDEF"


def test_team_member_remove_serializer_rejects_missing_user_code():
    serializer = TeamMemberRemoveSerializer(data={})

    assert not serializer.is_valid()
    assert "user_code" in serializer.errors
