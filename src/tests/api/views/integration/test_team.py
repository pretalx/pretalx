# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scopes_disabled

from pretalx.person.models.auth_token import ENDPOINTS
from tests.factories import (
    OrganiserFactory,
    TeamFactory,
    TeamInviteFactory,
    TrackFactory,
    UserApiTokenFactory,
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


# These fixtures shadow the api-level orga_user/orga_read_token/orga_write_token
# because team endpoints require can_change_teams, which the shared fixtures
# don't grant.


@pytest.fixture
def team(event):
    """Team with can_change_teams and full organiser permissions."""
    return TeamFactory(
        organiser=event.organiser,
        can_create_events=True,
        can_change_teams=True,
        can_change_organiser_settings=True,
        can_change_event_settings=True,
        can_change_submissions=True,
        all_events=True,
    )


@pytest.fixture
def orga_user(team):
    return make_orga_user(teams=[team])


@pytest.fixture
def orga_read_token(orga_user):
    return UserApiTokenFactory(
        user=orga_user, endpoints={key: ["list", "retrieve"] for key in ENDPOINTS}
    )


@pytest.fixture
def orga_write_token(orga_user):
    return UserApiTokenFactory(
        user=orga_user,
        endpoints={
            key: ["list", "retrieve", "create", "update", "destroy", "actions"]
            for key in ENDPOINTS
        },
    )


def _team_url(organiser, team_pk=None, suffix=""):
    base = f"/api/organisers/{organiser.slug}/teams/"
    if team_pk:
        base += f"{team_pk}/"
    return base + suffix


@pytest.mark.parametrize("item_count", (1, 3))
def test_team_list_returns_organiser_teams(
    client,
    event,
    orga_read_token,
    orga_user,
    team,
    item_count,
    django_assert_num_queries,
):
    """Team list returns organiser teams with constant query count."""
    with scopes_disabled():
        extra_teams = TeamFactory.create_batch(
            item_count,
            organiser=event.organiser,
            all_events=True,
            can_change_submissions=True,
        )
        for t in extra_teams:
            t.members.add(orga_user)

    with django_assert_num_queries(12):
        response = client.get(
            _team_url(event.organiser),
            follow=True,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == item_count + 1
    names = [r["name"] for r in data["results"]]
    assert team.name in names


def test_team_list_denied_for_reviewer_only(client, event, team):
    """A reviewer-only user without can_change_teams gets 403."""
    reviewer = make_orga_user(
        event, can_change_submissions=False, can_change_teams=False, is_reviewer=True
    )
    token = UserApiTokenFactory(
        user=reviewer,
        endpoints={
            key: ["list", "retrieve", "create", "update", "destroy", "actions"]
            for key in ENDPOINTS
        },
    )

    response = client.get(
        _team_url(event.organiser),
        follow=True,
        headers={"Authorization": f"Token {token.token}"},
    )

    assert response.status_code == 403


def test_team_detail_returns_team_data(client, orga_read_token, event, team):
    response = client.get(
        _team_url(event.organiser, team.pk),
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == team.name
    assert data["can_change_teams"] is True
    assert data["all_events"] is True


def test_team_detail_excludes_other_organiser_teams(client, orga_read_token, event):
    other_team = TeamFactory(
        organiser=OrganiserFactory(),
        can_change_teams=True,
        can_change_submissions=True,
        all_events=True,
    )

    response = client.get(
        _team_url(event.organiser, other_team.pk),
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 404


def test_team_detail_expand_related_fields(
    client, orga_read_token, event, team, orga_user
):
    """The ?expand= parameter inlines related objects."""
    invitation = TeamInviteFactory(team=team)
    with scopes_disabled():
        track = TrackFactory(event=event)
        team.limit_tracks.add(track)

    response = client.get(
        _team_url(event.organiser, team.pk) + "?expand=members,invites,limit_tracks",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == team.name
    assert len(data["members"]) == 1
    assert data["members"][0]["code"] == orga_user.code
    assert len(data["invites"]) == 1
    assert data["invites"][0]["email"] == invitation.email
    assert len(data["limit_tracks"]) == 1
    assert data["limit_tracks"][0]["name"]["en"] == track.name


def test_team_create_with_write_token(client, orga_write_token, event):
    organiser = event.organiser
    team_count = organiser.teams.count()

    response = client.post(
        _team_url(organiser),
        follow=True,
        data={
            "name": "New API Team",
            "can_change_submissions": True,
            "is_reviewer": False,
            "limit_events": [],
            "all_events": True,
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201, response.text
    with scopes_disabled():
        assert organiser.teams.count() == team_count + 1
        new_team = organiser.teams.get(name="New API Team")
        assert new_team.can_change_submissions is True
        assert new_team.is_reviewer is False
        assert new_team.all_events is True
        assert new_team.organiser == organiser


def test_team_create_rejected_without_events(client, orga_write_token, event):
    organiser = event.organiser
    team_count = organiser.teams.count()

    response = client.post(
        _team_url(organiser),
        follow=True,
        data={
            "name": "No Events Team",
            "can_change_submissions": True,
            "limit_events": [],
            "all_events": False,
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    with scopes_disabled():
        assert organiser.teams.count() == team_count


def test_team_create_rejected_without_permissions(client, orga_write_token, event):
    organiser = event.organiser
    team_count = organiser.teams.count()

    response = client.post(
        _team_url(organiser),
        follow=True,
        data={
            "name": "No Perms Team",
            "can_change_submissions": False,
            "is_reviewer": False,
            "all_events": True,
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    with scopes_disabled():
        assert organiser.teams.count() == team_count


def test_team_create_rejected_with_read_token(client, orga_read_token, event):
    organiser = event.organiser
    team_count = organiser.teams.count()

    response = client.post(
        _team_url(organiser),
        follow=True,
        data={"name": "Should Fail", "can_change_submissions": True},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 403
    assert organiser.teams.count() == team_count


def test_team_update_with_write_token(client, orga_write_token, event, team):
    response = client.patch(
        _team_url(event.organiser, team.pk),
        follow=True,
        data={"name": "Updated Team Name", "is_reviewer": True},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200
    team.refresh_from_db()
    assert team.name == "Updated Team Name"
    assert team.is_reviewer is True


def test_team_update_rejected_removing_last_permission(
    client, orga_write_token, event, team
):
    response = client.patch(
        _team_url(event.organiser, team.pk),
        follow=True,
        data={
            "is_reviewer": False,
            "can_create_events": False,
            "can_change_teams": False,
            "can_change_organiser_settings": False,
            "can_change_event_settings": False,
            "can_change_submissions": False,
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    team.refresh_from_db()
    assert team.can_change_submissions is True


def test_team_update_rejected_when_removing_last_can_change_teams(
    client, orga_write_token, event, team
):
    """Returns 400 via check_access_permissions even though the serializer validates."""
    response = client.patch(
        _team_url(event.organiser, team.pk),
        follow=True,
        data={"can_change_teams": False},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    team.refresh_from_db()
    assert team.can_change_teams is True


def test_team_delete_with_write_token(client, orga_write_token, event, team, orga_user):
    """Requires another team to cover access before deletion succeeds."""
    organiser = event.organiser
    with scopes_disabled():
        other = TeamFactory(
            organiser=organiser,
            can_change_teams=True,
            can_change_submissions=True,
            all_events=True,
        )
        other.members.add(orga_user)
    team_pk = team.pk
    team_count = organiser.teams.count()

    response = client.delete(
        _team_url(organiser, team_pk),
        follow=True,
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 204
    assert organiser.teams.count() == team_count - 1
    assert not organiser.teams.filter(pk=team_pk).exists()


def test_team_delete_rejected_when_last_team_with_can_change_teams(
    client, orga_write_token, event, team
):
    organiser = event.organiser
    team_count = organiser.teams.count()

    response = client.delete(
        _team_url(organiser, team.pk),
        follow=True,
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    assert organiser.teams.count() == team_count
    assert organiser.teams.filter(pk=team.pk).exists()


def test_team_invite_creates_invite(client, orga_write_token, event, team):
    invite_email = "new.invite@example.com"
    invite_count = team.invites.count()
    member_count = team.members.count()

    response = client.post(
        _team_url(event.organiser, team.pk, "invite/"),
        follow=True,
        data={"email": invite_email},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == invite_email
    assert team.invites.count() == invite_count + 1
    invite = team.invites.get(email=invite_email)
    assert data["token"] == invite.token
    assert team.members.count() == member_count


def test_team_invite_rejected_for_existing_member(
    client, orga_write_token, event, team, orga_user
):
    invite_count = team.invites.count()

    response = client.post(
        _team_url(event.organiser, team.pk, "invite/"),
        follow=True,
        data={"email": orga_user.email},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    assert "already a member" in response.text
    assert team.invites.count() == invite_count


def test_team_invite_rejected_for_already_invited_email(
    client, orga_write_token, event, team
):
    invitation = TeamInviteFactory(team=team)
    invite_count = team.invites.count()

    response = client.post(
        _team_url(event.organiser, team.pk, "invite/"),
        follow=True,
        data={"email": invitation.email},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    assert "already been invited" in response.text
    assert team.invites.count() == invite_count


def test_team_delete_invite_removes_invite_and_logs(
    client, orga_write_token, event, team
):
    invitation = TeamInviteFactory(team=team)
    invite_count = team.invites.count()

    response = client.delete(
        _team_url(event.organiser, team.pk, f"invites/{invitation.pk}/"),
        follow=True,
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 204
    with scopes_disabled():
        assert team.invites.count() == invite_count - 1
        assert not team.invites.filter(pk=invitation.pk).exists()
        assert (
            team.logged_actions()
            .filter(action_type="pretalx.team.invite.orga.retract")
            .exists()
        )


def test_team_delete_invite_returns_404_for_wrong_invite(
    client, orga_write_token, event, team
):
    response = client.delete(
        _team_url(event.organiser, team.pk, "invites/99999/"),
        follow=True,
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 404


def test_team_remove_member_removes_and_logs(
    client, orga_write_token, event, team, orga_user
):
    other_user = make_orga_user(teams=[team])
    member_count = team.members.count()

    response = client.post(
        _team_url(event.organiser, team.pk, "remove_member/"),
        follow=True,
        data={"user_code": other_user.code},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 204
    with scopes_disabled():
        team.refresh_from_db()
        assert team.members.count() == member_count - 1
        assert not team.members.filter(pk=other_user.pk).exists()
        assert (
            team.logged_actions()
            .filter(action_type="pretalx.team.remove_member")
            .exists()
        )


def test_team_remove_member_rejected_for_non_member(
    client, orga_write_token, event, team
):
    non_member = UserFactory()
    member_count = team.members.count()

    response = client.post(
        _team_url(event.organiser, team.pk, "remove_member/"),
        follow=True,
        data={"user_code": non_member.code},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    assert "not a member" in response.text
    assert team.members.count() == member_count


def test_team_remove_member_rejected_for_nonexistent_user(
    client, orga_write_token, event, team
):
    member_count = team.members.count()

    response = client.post(
        _team_url(event.organiser, team.pk, "remove_member/"),
        follow=True,
        data={"user_code": "NONEXISTENTCODE"},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    assert "not found" in response.text
    assert team.members.count() == member_count


def test_team_remove_member_rejected_when_would_leave_no_can_change_teams(
    client, orga_write_token, event, team, orga_user
):
    """Removing the last member from the only can_change_teams team returns 400
    via check_access_permissions."""
    member_count = team.members.count()

    response = client.post(
        _team_url(event.organiser, team.pk, "remove_member/"),
        follow=True,
        data={"user_code": orga_user.code},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    team.refresh_from_db()
    assert team.members.count() == member_count


def test_team_list_search_filters_by_name(client, orga_write_token, event, team):
    """The ?q= parameter filters teams by name."""
    with scopes_disabled():
        TeamFactory(
            organiser=event.organiser,
            name="Unique Searchable Name",
            can_change_submissions=True,
            all_events=True,
        )

    response = client.get(
        _team_url(event.organiser) + "?q=Unique+Searchable",
        follow=True,
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["results"][0]["name"] == "Unique Searchable Name"
