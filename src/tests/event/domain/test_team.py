# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core import mail as djmail

from pretalx.event.domain.team import (
    accept_team_invite,
    create_team_invites,
    remove_team_member,
    send_team_invite,
)
from pretalx.event.models import TeamInvite
from tests.factories import (
    EventFactory,
    OrganiserFactory,
    TeamFactory,
    TeamInviteFactory,
    UserApiTokenFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_create_team_invites_single_email_persists_and_sends():
    djmail.outbox = []
    team = TeamFactory()

    invites = create_team_invites(team=team, emails=["invitee@example.com"])

    assert len(invites) == 1
    assert invites[0].team == team
    assert invites[0].email == "invitee@example.com"
    assert invites[0].pk is not None
    assert len(djmail.outbox) == 1


def test_create_team_invites_multiple_emails():
    djmail.outbox = []
    team = TeamFactory()

    invites = create_team_invites(team=team, emails=["a@example.com", "b@example.com"])

    assert len(invites) == 2
    assert {i.email for i in invites} == {"a@example.com", "b@example.com"}
    assert all(i.team == team for i in invites)
    assert len(djmail.outbox) == 2


def test_create_team_invites_empty_list_is_noop():
    djmail.outbox = []
    team = TeamFactory()

    invites = create_team_invites(team=team, emails=[])

    assert invites == []
    assert djmail.outbox == []


def test_send_team_invite_delivers_email():
    djmail.outbox = []
    invite = TeamInviteFactory(email="speaker@example.com")

    send_team_invite(invite)

    assert len(djmail.outbox) == 1
    sent = djmail.outbox[0]
    assert sent.to == ["speaker@example.com"]
    assert invite.invitation_url in sent.body
    assert str(invite.team.organiser.name) in sent.body
    assert "invited" in sent.subject.lower()


def test_remove_team_member_removes_from_m2m():
    team = TeamFactory()
    user = UserFactory()
    actor = UserFactory()
    team.members.add(user)

    remove_team_member(team=team, member=user, actor=actor)

    assert list(team.members.all()) == []


def test_remove_team_member_logs_action():
    team = TeamFactory()
    user = UserFactory(name="Removed User", email="removed@example.com")
    actor = UserFactory()
    team.members.add(user)

    remove_team_member(team=team, member=user, actor=actor)

    log = team.logged_actions().filter(action_type="pretalx.team.remove_member").get()
    assert log.person == actor
    assert log.data["code"] == user.code
    assert log.data["email"] == "removed@example.com"


def test_accept_team_invite_adds_user_and_deletes_invite():
    team = TeamFactory()
    user = UserFactory()
    invite = TeamInviteFactory(team=team)
    invite_pk = invite.pk

    accept_team_invite(invite, user=user)

    assert user in team.members.all()
    from pretalx.event.models import TeamInvite  # noqa: PLC0415 -- local test import

    assert not TeamInvite.objects.filter(pk=invite_pk).exists()


def test_accept_team_invite_logs_against_organiser():
    team = TeamFactory()
    user = UserFactory()
    invite = TeamInviteFactory(team=team)

    accept_team_invite(invite, user=user)

    log = (
        team.organiser.logged_actions()
        .filter(action_type="pretalx.invite.orga.accept")
        .first()
    )
    assert log is not None
    assert log.person == user


def test_accept_team_invite_only_redeemed_once():
    team = TeamFactory()
    first_user = UserFactory()
    second_user = UserFactory()
    invite = TeamInviteFactory(team=team)
    first_copy = TeamInvite.objects.get(pk=invite.pk)
    second_copy = TeamInvite.objects.get(pk=invite.pk)

    accept_team_invite(first_copy, user=first_user)
    accept_team_invite(second_copy, user=second_user)

    assert list(team.members.all()) == [first_user]


def test_remove_team_member_updates_api_tokens():
    """When a member is removed, their API tokens scoped to this team's
    events should have their events updated."""
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    team = TeamFactory(organiser=organiser, all_events=True)
    user = UserFactory()
    actor = UserFactory()
    team.members.add(user)

    token = UserApiTokenFactory(user=user)
    token.events.add(event)

    remove_team_member(team=team, member=user, actor=actor)

    token.refresh_from_db()
    assert list(token.events.all()) == []
