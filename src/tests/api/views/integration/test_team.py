# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scopes_disabled

from pretalx.person.models.auth_token import ENDPOINTS
from tests.factories import (
    EventFactory,
    OrganiserFactory,
    TeamFactory,
    TeamInviteFactory,
    TrackFactory,
    UserApiTokenFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


# These fixtures shadow the api-level orga_user/orga_read_token/orga_write_token
# because team endpoints require can_change_teams, which the shared fixtures
# don't grant.


@pytest.fixture
def team(event):
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
def orga_read_token(orga_user, event):
    return UserApiTokenFactory(
        user=orga_user,
        limit_events=[event],
        endpoints={key: ["list", "retrieve"] for key in ENDPOINTS},
    )


@pytest.fixture
def orga_write_token(orga_user, event):
    return UserApiTokenFactory(
        user=orga_user,
        limit_events=[event],
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
    with scopes_disabled():
        extra_teams = TeamFactory.create_batch(
            item_count,
            organiser=event.organiser,
            all_events=True,
            can_change_submissions=True,
        )
        for t in extra_teams:
            t.members.add(orga_user)
        searchable = TeamFactory(
            organiser=event.organiser,
            name="Unique Searchable Name",
            can_change_submissions=True,
            all_events=True,
        )
    headers = {"Authorization": f"Token {orga_read_token.token}"}

    with django_assert_num_queries(14):
        response = client.get(_team_url(event.organiser), follow=True, headers=headers)
    searched = client.get(
        _team_url(event.organiser) + "?q=Unique+Searchable",
        follow=True,
        headers=headers,
    )

    assert response.status_code == 200
    assert {r["id"] for r in response.json()["results"]} == {
        team.pk,
        searchable.pk,
        *(t.pk for t in extra_teams),
    }
    assert searched.status_code == 200
    assert [r["id"] for r in searched.json()["results"]] == [searchable.pk]


def test_team_list_denied_for_reviewer_only(client, event, team):
    reviewer = make_orga_user(
        event, can_change_submissions=False, can_change_teams=False, is_reviewer=True
    )
    token = UserApiTokenFactory(
        user=reviewer,
        limit_events=[event],
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


def test_team_endpoints_denied_for_event_scoped_token(client, event, team, orga_user):
    with scopes_disabled():
        EventFactory(organiser=event.organiser)  # a second, out-of-scope event
    token = UserApiTokenFactory(
        user=orga_user,
        limit_events=[event],
        endpoints={
            key: ["list", "retrieve", "create", "update", "destroy", "actions"]
            for key in ENDPOINTS
        },
    )
    headers = {"Authorization": f"Token {token.token}"}

    listing = client.get(_team_url(event.organiser), follow=True, headers=headers)
    assert listing.status_code == 403

    invite = client.post(
        _team_url(event.organiser, team.pk, "invite/"),
        follow=True,
        data={"email": "intruder@example.com"},
        content_type="application/json",
        headers=headers,
    )
    assert invite.status_code == 403
    assert team.invites.count() == 0


def test_team_list_allowed_for_all_events_token(client, event, team, orga_user):
    token = UserApiTokenFactory(
        user=orga_user,
        all_events=True,
        endpoints={key: ["list", "retrieve"] for key in ENDPOINTS},
    )
    with scopes_disabled():
        EventFactory(organiser=event.organiser)

    response = client.get(
        _team_url(event.organiser),
        follow=True,
        headers={"Authorization": f"Token {token.token}"},
    )

    assert response.status_code == 200
    assert team.name in [t["name"] for t in response.json()["results"]]


def test_team_detail_with_read_token(client, orga_read_token, event, team, orga_user):
    invitation = TeamInviteFactory(team=team)
    other_team = TeamFactory(
        organiser=OrganiserFactory(),
        can_change_teams=True,
        can_change_submissions=True,
        all_events=True,
    )
    with scopes_disabled():
        track = TrackFactory(event=event)
        team.limit_tracks.add(track)
    headers = {"Authorization": f"Token {orga_read_token.token}"}

    response = client.get(
        _team_url(event.organiser, team.pk), follow=True, headers=headers
    )
    expanded = client.get(
        _team_url(event.organiser, team.pk) + "?expand=members,invites,limit_tracks",
        follow=True,
        headers=headers,
    )
    foreign = client.get(
        _team_url(event.organiser, other_team.pk), follow=True, headers=headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == team.name
    assert data["can_change_teams"] is True
    assert data["all_events"] is True
    assert data["members"] == [orga_user.code]
    assert data["invites"] == [invitation.pk]
    assert data["limit_tracks"] == [track.pk]
    assert expanded.status_code == 200
    data = expanded.json()
    assert [m["code"] for m in data["members"]] == [orga_user.code]
    assert [i["email"] for i in data["invites"]] == [invitation.email]
    assert [t["name"]["en"] for t in data["limit_tracks"]] == [track.name]
    assert foreign.status_code == 404


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


@pytest.mark.parametrize(
    "data",
    (
        {
            "name": "No Events Team",
            "can_change_submissions": True,
            "limit_events": [],
            "all_events": False,
        },
        {
            "name": "No Perms Team",
            "can_change_submissions": False,
            "is_reviewer": False,
            "all_events": True,
        },
    ),
    ids=("without_events", "without_permissions"),
)
def test_team_create_rejected_for_invalid_team(client, orga_write_token, event, data):
    organiser = event.organiser
    team_count = organiser.teams.count()

    response = client.post(
        _team_url(organiser),
        follow=True,
        data=data,
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


@pytest.mark.parametrize(
    "data",
    (
        {
            "is_reviewer": False,
            "can_create_events": False,
            "can_change_teams": False,
            "can_change_organiser_settings": False,
            "can_change_event_settings": False,
            "can_change_submissions": False,
        },
        {"can_change_teams": False},
    ),
    ids=("removing_last_permission", "removing_last_can_change_teams"),
)
def test_team_update_rejected(client, orga_write_token, event, team, data):
    response = client.patch(
        _team_url(event.organiser, team.pk),
        follow=True,
        data=data,
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    team.refresh_from_db()
    assert team.can_change_submissions is True
    assert team.can_change_teams is True


def test_team_delete_with_write_token(client, orga_write_token, event, team, orga_user):
    organiser = event.organiser
    url = _team_url(organiser, team.pk)
    headers = {"Authorization": f"Token {orga_write_token.token}"}
    team_count = organiser.teams.count()

    rejected = client.delete(url, follow=True, headers=headers)

    assert rejected.status_code == 400
    assert organiser.teams.count() == team_count
    assert organiser.teams.filter(pk=team.pk).exists()

    with scopes_disabled():
        other = TeamFactory(
            organiser=organiser,
            can_change_teams=True,
            can_change_submissions=True,
            all_events=True,
        )
        other.members.add(orga_user)

    response = client.delete(url, follow=True, headers=headers)

    assert response.status_code == 204
    assert list(organiser.teams.all()) == [other]


def test_team_invite_lifecycle(client, orga_write_token, event, team, orga_user):
    invite_email = "new.invite@example.com"
    headers = {"Authorization": f"Token {orga_write_token.token}"}
    invite_url = _team_url(event.organiser, team.pk, "invite/")

    response = client.post(
        invite_url,
        follow=True,
        data={"email": invite_email},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()
    invite = team.invites.get()
    assert data == {"id": invite.pk, "email": invite_email}
    assert list(team.members.all()) == [orga_user]

    repeated = client.post(
        invite_url,
        follow=True,
        data={"email": invite_email},
        content_type="application/json",
        headers=headers,
    )
    member = client.post(
        invite_url,
        follow=True,
        data={"email": orga_user.email},
        content_type="application/json",
        headers=headers,
    )

    assert repeated.status_code == 400
    assert repeated.json() == ["This user has already been invited to the team."]
    assert member.status_code == 400
    assert member.json() == ["This user is already a member of the team."]
    assert list(team.invites.all()) == [invite]

    delete_url = _team_url(event.organiser, team.pk, f"invites/{invite.pk}/")
    deleted = client.delete(delete_url, follow=True, headers=headers)
    missing = client.delete(delete_url, follow=True, headers=headers)

    assert deleted.status_code == 204
    assert missing.status_code == 404
    with scopes_disabled():
        assert team.invites.count() == 0
        assert (
            team.logged_actions()
            .filter(action_type="pretalx.team.invite.orga.retract")
            .exists()
        )


def test_team_remove_member(client, orga_write_token, event, team, orga_user):
    other_user = make_orga_user(teams=[team])
    url = _team_url(event.organiser, team.pk, "remove_member/")
    headers = {"Authorization": f"Token {orga_write_token.token}"}

    response = client.post(
        url,
        follow=True,
        data={"user_code": other_user.code},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 204
    with scopes_disabled():
        assert list(team.members.all()) == [orga_user]
        assert (
            team.logged_actions()
            .filter(action_type="pretalx.team.remove_member")
            .exists()
        )

    non_member = client.post(
        url,
        follow=True,
        data={"user_code": other_user.code},
        content_type="application/json",
        headers=headers,
    )
    unknown = client.post(
        url,
        follow=True,
        data={"user_code": "NONEXISTENTCODE"},
        content_type="application/json",
        headers=headers,
    )
    last_admin = client.post(
        url,
        follow=True,
        data={"user_code": orga_user.code},
        content_type="application/json",
        headers=headers,
    )

    assert non_member.status_code == 400
    assert "not a member" in non_member.text
    assert unknown.status_code == 400
    assert "not found" in unknown.text
    assert last_admin.status_code == 400
    assert list(team.members.all()) == [orga_user]
