# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core import mail as djmail
from django.test import override_settings
from django.urls import reverse
from django_scopes import scopes_disabled

from pretalx.event.models import Event, Organiser, Team, TeamInvite
from tests.factories import (
    SpeakerFactory,
    SubmissionFactory,
    TeamFactory,
    TeamInviteFactory,
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

TEAM_DATA = {
    "all_events": True,
    "can_change_submissions": True,
    "can_change_organiser_settings": True,
    "can_change_event_settings": True,
    "can_change_teams": True,
    "can_create_events": True,
    "form": "team",
}


def _team_url(event, name, **kwargs):
    return reverse(
        f"orga:organiser.teams.{name}",
        kwargs={"organiser": event.organiser.slug, **kwargs},
    )


def test_organiser_views_deny_anonymous_and_unrelated_users(client, event):
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
        member = UserFactory()
        team.members.add(member)
    organiser = event.organiser
    get_urls = (
        organiser.orga_urls.settings,
        _team_url(event, "list"),
        reverse("orga:organiser.speakers", kwargs={"organiser": organiser.slug}),
    )
    member_kwargs = {"team_pk": team.pk, "user_pk": member.pk}
    post_urls = (
        organiser.orga_urls.delete,
        _team_url(event, "members.delete", **member_kwargs),
        _team_url(event, "members.reset", **member_kwargs),
    )

    for url in get_urls:
        response = client.get(url)
        assert response.status_code == 302, url
        assert response.url == f"/orga/login/?next={url}", url

    client.force_login(UserFactory())
    for url in get_urls:
        assert client.get(url).status_code == 404, url
    for url in post_urls:
        assert client.post(url).status_code == 404, url

    client.force_login(make_orga_user(event, can_change_organiser_settings=True))
    assert client.post(organiser.orga_urls.delete, follow=True).status_code == 404

    assert Organiser.objects.filter(pk=organiser.pk).exists()
    assert list(team.members.all()) == [member]
    member.refresh_from_db()
    assert not member.pw_reset_token


def test_organiser_detail_shows_and_edits_name(client, event):
    user = make_orga_user(event, can_change_organiser_settings=True)
    client.force_login(user)

    response = client.get(event.organiser.orga_urls.settings)

    assert response.status_code == 200
    assert str(event.organiser.name) in response.content.decode()

    response = client.post(
        event.organiser.orga_urls.settings,
        data={"name_0": "New Organiser Name", "name_1": "New Organiser Name"},
        follow=True,
    )

    assert response.status_code == 200
    event.organiser.refresh_from_db()
    assert str(event.organiser.name) == "New Organiser Name"


def test_organiser_create_and_delete_by_administrator(client, event):
    admin = UserFactory(is_administrator=True)
    client.force_login(admin)
    organiser = event.organiser

    response = client.post(
        reverse("orga:organiser.create"),
        data={
            "name_0": "New Organiser",
            "name_1": "New Organiser",
            "slug": "new-organiser",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert str(Organiser.objects.get(slug="new-organiser").name) == "New Organiser"

    response = client.get(organiser.orga_urls.delete, follow=True)
    assert response.status_code == 200

    response = client.post(organiser.orga_urls.delete, follow=True)

    assert response.status_code == 200
    assert list(Organiser.objects.values_list("slug", flat=True)) == ["new-organiser"]
    with scopes_disabled():
        assert not Event.objects.filter(pk=event.pk).exists()


def test_team_list_requires_team_permission(client, event):
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, name="Visible Team", all_events=True
        )
    url = _team_url(event, "list")

    client.force_login(make_orga_user(event, can_change_teams=False))

    assert client.get(url).status_code == 404

    client.force_login(make_orga_user(event, can_change_teams=True))
    response = client.get(url)

    assert response.status_code == 200
    assert str(team.name) in response.content.decode()


def test_team_create_requires_an_event(client, event):
    user = make_orga_user(event, can_change_teams=True)
    client.force_login(user)
    initial_count = event.organiser.teams.count()
    url = _team_url(event, "create")
    data = {**TEAM_DATA, "name": "New Team", "organiser": event.organiser.pk}
    del data["all_events"]

    response = client.post(url, data=data, follow=True)

    assert response.status_code == 200
    assert event.organiser.teams.count() == initial_count

    response = client.post(url, data={**data, "limit_events": event.pk}, follow=True)

    assert response.status_code == 200
    assert event.organiser.teams.count() == initial_count + 1
    with scopes_disabled():
        assert list(event.organiser.teams.get(name="New Team").limit_events.all()) == [
            event
        ]


def test_team_update_page_edits_team_and_invites_members(client, event):
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser,
            name="Original",
            can_change_teams=True,
            can_create_events=True,
            all_events=True,
        )
        member = UserFactory()
        team.members.add(member)
        SpeakerFactory(event=event, user=member)
        TeamInviteFactory(team=team, email="pending@example.com")
    user = make_orga_user(event, can_change_teams=True)
    client.force_login(user)
    djmail.outbox = []
    url = _team_url(event, "update", pk=team.pk)

    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Original" in content
    assert member.name in content
    assert "status-dot" not in content

    response = client.post(
        url, data={**TEAM_DATA, "name": "Updated Team Name"}, follow=True
    )

    assert response.status_code == 200
    assert [str(message) for message in response.context["messages"]] == [
        "Your changes have been saved."
    ]
    team.refresh_from_db()
    assert team.name == "Updated Team Name"
    assert team.can_create_events

    response = client.post(
        url,
        data={**TEAM_DATA, "can_create_events": False, "name": "No Create Events"},
        follow=True,
    )

    assert response.status_code == 200
    assert [str(message) for message in response.context["messages"]] == [
        "Your changes have been saved.",
        "Nobody on your teams has the permission to create new events.",
    ]
    team.refresh_from_db()
    assert team.name == "No Create Events"
    assert not team.can_create_events

    response = client.post(
        url, data={"invite-emails": "", "form": "invite"}, follow=True
    )

    assert response.status_code == 200
    assert list(team.invites.values_list("email", flat=True)) == ["pending@example.com"]
    assert djmail.outbox == []

    response = client.post(
        url,
        data={"invite-emails": "newinvite@example.com", "form": "invite"},
        follow=True,
    )

    assert response.status_code == 200
    assert list(team.invites.order_by("pk").values_list("email", flat=True)) == [
        "pending@example.com",
        "newinvite@example.com",
    ]
    assert [mail.to for mail in djmail.outbox] == [["newinvite@example.com"]]

    response = client.post(
        url,
        data={
            "invite-emails": "first@example.com,second@example.com",
            "form": "invite",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert team.invites.count() == 4
    assert [mail.to for mail in djmail.outbox] == [
        ["newinvite@example.com"],
        ["first@example.com"],
        ["second@example.com"],
    ]


def test_last_team_with_change_teams_permission_is_protected(client, event):
    with scopes_disabled():
        event.organiser.teams.update(can_change_teams=False)
        team = TeamFactory(
            organiser=event.organiser,
            name="Only Admin Team",
            can_change_teams=True,
            all_events=True,
        )
        user = make_orga_user(teams=[team])
        other_member = UserFactory()
        team.members.add(other_member)
    client.force_login(user)
    update_url = _team_url(event, "update", pk=team.pk)
    delete_url = _team_url(event, "delete", pk=team.pk)

    response = client.get(update_url)

    assert response.status_code == 200
    content = response.content.decode()
    assert f'href="{delete_url}"' not in content
    assert 'aria-disabled="true"' in content
    assert "at least one team with the permission to change teams" in content

    response = client.post(
        update_url,
        data={
            **TEAM_DATA,
            "can_change_organiser_settings": False,
            "can_change_teams": False,
            "name": "Removed Permissions",
        },
        follow=True,
    )

    assert response.status_code == 200
    team.refresh_from_db()
    assert team.can_change_teams
    assert team.name == "Only Admin Team"

    response = client.post(delete_url, follow=True)

    assert response.status_code == 200
    assert Team.objects.filter(pk=team.pk).exists()

    response = client.post(
        _team_url(event, "members.delete", team_pk=team.pk, user_pk=other_member.pk),
        follow=True,
    )

    assert response.status_code == 200
    assert list(team.members.all()) == [user]

    response = client.post(
        _team_url(event, "members.delete", team_pk=team.pk, user_pk=user.pk),
        follow=True,
    )

    assert response.status_code == 200
    assert list(team.members.all()) == [user]


def test_team_delete_when_another_team_keeps_change_teams(client, event):
    with scopes_disabled():
        backup = TeamFactory(
            organiser=event.organiser,
            can_change_teams=True,
            can_create_events=True,
            can_change_event_settings=True,
            all_events=True,
        )
        settings_team = TeamFactory(
            organiser=event.organiser,
            name="Settings",
            can_change_organiser_settings=True,
            all_events=True,
        )
        settings_team.members.add(UserFactory())
        deletable = TeamFactory(
            organiser=event.organiser,
            name="Deletable",
            can_change_teams=True,
            all_events=True,
        )
        deletable.members.add(UserFactory())
    user = make_orga_user(teams=[backup])
    client.force_login(user)
    delete_url = _team_url(event, "delete", pk=deletable.pk)

    response = client.get(_team_url(event, "update", pk=deletable.pk))

    assert response.status_code == 200
    content = response.content.decode()
    assert f'href="{delete_url}"' in content
    assert 'aria-disabled="true"' not in content

    response = client.post(delete_url, follow=True)

    assert response.status_code == 200
    assert [str(message) for message in response.context["messages"]] == [
        "The team was removed."
    ]
    assert not Team.objects.filter(pk=deletable.pk).exists()

    response = client.post(_team_url(event, "delete", pk=settings_team.pk), follow=True)

    assert response.status_code == 200
    assert [str(message) for message in response.context["messages"]] == [
        "The team was removed.",
        "Nobody on your teams has the permission to change organiser-level settings.",
    ]
    assert set(Team.objects.filter(organiser=event.organiser)) == {backup}


def test_team_invite_resend_and_uninvite(client, event):
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
        invite = TeamInviteFactory(team=team, email="confirm@example.com")
    user = make_orga_user(event, can_change_teams=True)
    client.force_login(user)
    djmail.outbox = []
    invite_kwargs = {"pk": team.pk, "invite_pk": invite.pk}
    resend_url = _team_url(event, "invites.resend", **invite_kwargs)
    uninvite_url = _team_url(event, "invites.uninvite", **invite_kwargs)

    for url in (resend_url, uninvite_url):
        response = client.get(url)
        assert response.status_code == 200, url
        content = response.content.decode()
        assert "confirm@example.com" in content, url
        assert f'href="{team.orga_urls.base}"' in content, url

    response = client.post(resend_url, follow=True)

    assert response.status_code == 200
    assert list(team.invites.all()) == [invite]
    assert [mail.to for mail in djmail.outbox] == [["confirm@example.com"]]

    response = client.post(uninvite_url, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert not TeamInvite.objects.filter(pk=invite.pk).exists()


def test_team_member_reset_password_and_delete(client, event):
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
        member = UserFactory(name="Member Person", email="member@example.com")
        team.members.add(member)
    user = make_orga_user(
        event,
        can_change_teams=True,
        can_create_events=True,
        can_change_organiser_settings=True,
        can_change_event_settings=True,
    )
    client.force_login(user)
    djmail.outbox = []
    member_kwargs = {"team_pk": team.pk, "user_pk": member.pk}
    delete_url = _team_url(event, "members.delete", **member_kwargs)
    reset_url = _team_url(event, "members.reset", **member_kwargs)

    response = client.get(delete_url)

    assert response.status_code == 200
    assert "Member Person (member@example.com)" in response.content.decode()

    response = client.post(reset_url, follow=True)

    assert response.status_code == 200
    member.refresh_from_db()
    first_token = member.pw_reset_token
    assert first_token
    assert [mail.to for mail in djmail.outbox] == [["member@example.com"]]

    response = client.post(reset_url, follow=True)

    assert response.status_code == 200
    member.refresh_from_db()
    assert member.pw_reset_token
    assert member.pw_reset_token != first_token
    assert len(djmail.outbox) == 2

    response = client.post(delete_url, follow=True)

    assert response.status_code == 200
    assert list(team.members.all()) == []


@override_settings(
    MAILERS={
        "default": {
            "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "OPTIONS": {"host": "localhost", "port": 1},
        }
    },
    DEBUG=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
def test_team_reset_password_shows_error_on_mail_failure(client, event):
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
        member = UserFactory()
        team.members.add(member)
    user = make_orga_user(event, can_change_teams=True)
    client.force_login(user)

    response = client.post(
        _team_url(event, "members.reset", team_pk=team.pk, user_pk=member.pk),
        follow=True,
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "could not be sent" in content


@pytest.mark.parametrize("item_count", (1, 3))
def test_organiser_speaker_list_shows_speakers(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        speakers = []
        for _ in range(item_count):
            speaker = SpeakerFactory(event=event)
            sub = SubmissionFactory(event=event, state="accepted")
            sub.speakers.add(speaker)
            speakers.append(speaker)
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    url = reverse("orga:organiser.speakers", kwargs={"organiser": event.organiser.slug})
    with django_assert_num_queries(12):
        response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    for speaker in speakers:
        assert speaker.user.name in content


def test_organiser_speaker_list_sorts_and_hides_without_event_access(client, event):
    with scopes_disabled():
        for name in ("Zed Zebra", "Adam Aardvark"):
            speaker = SpeakerFactory(event=event, user__name=name)
            sub = SubmissionFactory(event=event, state="accepted")
            sub.speakers.add(speaker)
    url = reverse("orga:organiser.speakers", kwargs={"organiser": event.organiser.slug})
    client.force_login(make_orga_user(event, can_change_submissions=True))

    for sort, first, second in (
        ("name", "Adam Aardvark", "Zed Zebra"),
        ("-name", "Zed Zebra", "Adam Aardvark"),
    ):
        response = client.get(url, {"sort": sort})
        assert response.status_code == 200, sort
        content = response.content.decode()
        assert content.index(first) < content.index(second), sort

    client.force_login(
        make_orga_user(event, can_change_submissions=False, can_change_teams=True)
    )
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Zed Zebra" not in content
    assert "Adam Aardvark" not in content
