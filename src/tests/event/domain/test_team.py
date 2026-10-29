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


def test_create_team_invites_persists_and_sends_one_mail_per_email():
    djmail.outbox = []
    team = TeamFactory()

    assert create_team_invites(team=team, emails=[]) == []
    assert djmail.outbox == []

    invites = create_team_invites(team=team, emails=["a@example.com", "b@example.com"])

    assert [(invite.team, invite.email) for invite in invites] == [
        (team, "a@example.com"),
        (team, "b@example.com"),
    ]
    assert set(TeamInvite.objects.filter(team=team)) == set(invites)
    assert [sent.to for sent in djmail.outbox] == [["a@example.com"], ["b@example.com"]]


def test_send_team_invite_delivers_email():
    djmail.outbox = []
    invite = TeamInviteFactory(email="speaker@example.com")

    send_team_invite(invite)

    assert len(djmail.outbox) == 1
    sent = djmail.outbox[0]
    assert sent.to == ["speaker@example.com"]
    assert sent.subject == "You have been invited to an organiser team"
    assert invite.invitation_url in sent.body
    assert str(invite.team.organiser.name) in sent.body


def test_remove_team_member_removes_member_logs_and_revokes_api_tokens():
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    team = TeamFactory(organiser=organiser, all_events=True)
    user = UserFactory(name="Removed User", email="removed@example.com")
    actor = UserFactory()
    team.members.add(user)
    limited_token = UserApiTokenFactory(user=user)
    limited_token.limit_events.add(event)
    all_events_token = UserApiTokenFactory(user=user, all_events=True, expires=None)

    remove_team_member(team=team, member=user, actor=actor)

    assert list(team.members.all()) == []
    log = team.logged_actions().filter(action_type="pretalx.team.remove_member").get()
    assert log.person == actor
    assert log.data["code"] == user.code
    assert log.data["email"] == "removed@example.com"
    limited_token.refresh_from_db()
    all_events_token.refresh_from_db()
    assert list(limited_token.limit_events.all()) == []
    assert not all_events_token.is_active


def test_remove_team_member_keeps_all_events_tokens_with_remaining_access():
    organiser = OrganiserFactory()
    EventFactory(organiser=organiser)
    team = TeamFactory(organiser=organiser, all_events=True)
    other_team = TeamFactory(organiser=organiser, all_events=True)
    user = UserFactory()
    actor = UserFactory()
    team.members.add(user)
    other_team.members.add(user)
    token = UserApiTokenFactory(user=user, all_events=True, expires=None)

    remove_team_member(team=team, member=user, actor=actor)

    token.refresh_from_db()
    assert token.expires is None


def test_accept_team_invite_adds_user_logs_and_is_redeemed_once():
    team = TeamFactory()
    first_user = UserFactory()
    second_user = UserFactory()
    invite = TeamInviteFactory(team=team)
    first_copy = TeamInvite.objects.get(pk=invite.pk)
    second_copy = TeamInvite.objects.get(pk=invite.pk)

    accept_team_invite(first_copy, user=first_user)

    assert list(team.members.all()) == [first_user]
    assert not TeamInvite.objects.filter(pk=invite.pk).exists()
    log = (
        team.organiser.logged_actions()
        .filter(action_type="pretalx.invite.orga.accept")
        .get()
    )
    assert log.person == first_user

    accept_team_invite(second_copy, user=second_user)

    assert list(team.members.all()) == [first_user]
