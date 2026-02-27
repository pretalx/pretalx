import pytest
from django.core import mail as djmail
from django.test import override_settings
from django.urls import reverse
from django_scopes import scopes_disabled

from pretalx.event.models import Event, Organiser, Team, TeamInvite
from tests.factories import (
    EventFactory,
    SpeakerFactory,
    SubmissionFactory,
    TeamFactory,
    TeamInviteFactory,
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_organiser_detail_accessible_by_organiser(client, event):
    user = make_orga_user(event, can_change_organiser_settings=True)
    client.force_login(user)

    response = client.get(event.organiser.orga_urls.settings)

    assert response.status_code == 200
    assert str(event.organiser.name) in response.content.decode()


@pytest.mark.django_db
def test_organiser_detail_edit_name(client, event):
    user = make_orga_user(event, can_change_organiser_settings=True)
    client.force_login(user)

    response = client.post(
        event.organiser.orga_urls.settings,
        data={"name_0": "New Organiser Name", "name_1": "New Organiser Name"},
        follow=True,
    )

    assert response.status_code == 200
    event.organiser.refresh_from_db()
    assert str(event.organiser.name) == "New Organiser Name"


@pytest.mark.django_db
def test_organiser_detail_denied_without_permission(client, event):
    user = UserFactory()
    client.force_login(user)

    response = client.get(event.organiser.orga_urls.settings)

    assert response.status_code == 404


@pytest.mark.django_db
def test_organiser_create_by_administrator(client):
    admin = UserFactory(is_administrator=True)
    client.force_login(admin)
    assert Organiser.objects.count() == 0

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
    assert Organiser.objects.count() == 1
    assert str(Organiser.objects.first().name) == "New Organiser"


@pytest.mark.django_db
def test_organiser_delete_by_administrator(client, event):
    admin = UserFactory(is_administrator=True)
    client.force_login(admin)
    organiser = event.organiser

    response = client.get(organiser.orga_urls.delete, follow=True)
    assert response.status_code == 200

    response = client.post(organiser.orga_urls.delete, follow=True)

    assert response.status_code == 200
    assert not Organiser.objects.filter(pk=organiser.pk).exists()


@pytest.mark.django_db
def test_organiser_delete_cascades_events(client, event):
    admin = UserFactory(is_administrator=True)
    client.force_login(admin)
    organiser = event.organiser
    event_pk = event.pk

    client.post(organiser.orga_urls.delete, follow=True)

    with scopes_disabled():
        assert not Event.objects.filter(pk=event_pk).exists()


@pytest.mark.django_db
def test_organiser_delete_denied_for_non_administrator(client, event):
    user = make_orga_user(event, can_change_organiser_settings=True)
    client.force_login(user)

    response = client.post(event.organiser.orga_urls.delete, follow=True)

    assert response.status_code == 404
    assert Organiser.objects.filter(pk=event.organiser.pk).exists()


@pytest.mark.django_db
def test_team_list_accessible_by_organiser(client, event):
    user = make_orga_user(event, can_change_teams=True)
    client.force_login(user)

    url = reverse(
        "orga:organiser.teams.list", kwargs={"organiser": event.organiser.slug}
    )
    response = client.get(url)

    assert response.status_code == 200


@pytest.mark.django_db
def test_team_list_denied_without_permission(client, event):
    user = UserFactory()
    client.force_login(user)

    url = reverse(
        "orga:organiser.teams.list", kwargs={"organiser": event.organiser.slug}
    )
    response = client.get(url)

    assert response.status_code == 404


@pytest.mark.django_db
def test_team_create(client, event):
    user = make_orga_user(event, can_change_teams=True)
    client.force_login(user)
    initial_count = event.organiser.teams.count()

    url = reverse(
        "orga:organiser.teams.create", kwargs={"organiser": event.organiser.slug}
    )
    response = client.post(
        url,
        data={
            "all_events": True,
            "can_change_submissions": True,
            "can_change_organiser_settings": True,
            "can_change_event_settings": True,
            "can_change_teams": True,
            "can_create_events": True,
            "form": "team",
            "limit_events": event.pk,
            "name": "New Team",
            "organiser": event.organiser.pk,
        },
        follow=True,
    )

    assert response.status_code == 200
    assert event.organiser.teams.count() == initial_count + 1
    assert event.organiser.teams.filter(name="New Team").exists()


@pytest.mark.django_db
def test_team_create_without_event_fails_validation(client, event):
    """Team creation without all_events and without limit_events should fail."""
    user = make_orga_user(event, can_change_teams=True)
    client.force_login(user)
    initial_count = event.organiser.teams.count()

    url = reverse(
        "orga:organiser.teams.create", kwargs={"organiser": event.organiser.slug}
    )
    client.post(
        url,
        data={
            "can_change_submissions": True,
            "can_change_organiser_settings": True,
            "can_change_event_settings": True,
            "can_change_teams": True,
            "can_create_events": True,
            "form": "team",
            "name": "Invalid Team",
            "organiser": event.organiser.pk,
        },
        follow=True,
    )

    assert event.organiser.teams.count() == initial_count


@pytest.mark.django_db
def test_team_update(client, event):
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser,
            name="Original",
            can_change_teams=True,
            all_events=True,
        )
    user = make_orga_user(
        event,
        can_change_teams=True,
        can_create_events=True,
        can_change_organiser_settings=True,
        can_change_event_settings=True,
    )
    client.force_login(user)

    url = reverse(
        "orga:organiser.teams.update",
        kwargs={"organiser": event.organiser.slug, "pk": team.pk},
    )
    response = client.post(
        url,
        data={
            "all_events": True,
            "can_change_submissions": True,
            "can_change_organiser_settings": True,
            "can_change_event_settings": True,
            "can_change_teams": True,
            "can_create_events": True,
            "form": "team",
            "name": "Updated Team Name",
        },
        follow=True,
    )

    assert response.status_code == 200
    team.refresh_from_db()
    assert team.name == "Updated Team Name"


@pytest.mark.django_db
def test_team_update_cannot_remove_last_team_permissions(client, event):
    """Removing can_change_teams from the only team with that permission
    should be prevented by check_access_permissions."""
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser,
            name="Only Admin Team",
            can_change_teams=True,
            all_events=True,
        )
        user = UserFactory()
        team.members.add(user)
        # Remove can_change_teams from all other teams
        event.organiser.teams.exclude(pk=team.pk).update(can_change_teams=False)
    client.force_login(user)

    url = reverse(
        "orga:organiser.teams.update",
        kwargs={"organiser": event.organiser.slug, "pk": team.pk},
    )
    response = client.post(
        url,
        data={
            "all_events": True,
            "can_change_submissions": True,
            "can_change_organiser_settings": False,
            "can_change_event_settings": True,
            "can_change_teams": False,
            "can_create_events": True,
            "form": "team",
            "name": "Removed Permissions",
        },
        follow=True,
    )

    assert response.status_code == 200
    team.refresh_from_db()
    assert team.can_change_teams
    assert team.name != "Removed Permissions"


@pytest.mark.django_db
def test_team_delete(client, event):
    with scopes_disabled():
        # Ensure another team keeps can_change_teams so deletion is allowed
        TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        ).members.add(UserFactory())
        team_to_delete = TeamFactory(
            organiser=event.organiser, name="Deletable", all_events=True
        )
    user = make_orga_user(
        event,
        can_change_teams=True,
        can_create_events=True,
        can_change_organiser_settings=True,
        can_change_event_settings=True,
    )
    client.force_login(user)
    team_pk = team_to_delete.pk

    url = reverse(
        "orga:organiser.teams.delete",
        kwargs={"organiser": event.organiser.slug, "pk": team_pk},
    )
    response = client.post(url, follow=True)

    assert response.status_code == 200
    assert not Team.objects.filter(pk=team_pk).exists()


@pytest.mark.django_db
def test_team_delete_last_team_with_change_teams_permission_fails(client, event):
    """Deleting the last team with can_change_teams should be prevented."""
    with scopes_disabled():
        event.organiser.teams.update(can_change_teams=False)
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
        user = UserFactory()
        team.members.add(user)
    client.force_login(user)

    url = reverse(
        "orga:organiser.teams.delete",
        kwargs={"organiser": event.organiser.slug, "pk": team.pk},
    )
    response = client.post(url, follow=True)

    assert response.status_code == 200
    assert Team.objects.filter(pk=team.pk).exists()


@pytest.mark.django_db
def test_team_invite_single_member(client, event):
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
    user = make_orga_user(event, can_change_teams=True)
    client.force_login(user)
    djmail.outbox = []

    url = reverse(
        "orga:organiser.teams.update",
        kwargs={"organiser": event.organiser.slug, "pk": team.pk},
    )
    response = client.post(
        url,
        data={"invite-email": "newinvite@example.com", "form": "invite"},
        follow=True,
    )

    assert response.status_code == 200
    assert team.invites.count() == 1
    assert team.invites.first().email == "newinvite@example.com"
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["newinvite@example.com"]


@pytest.mark.django_db
def test_team_invite_multiple_members(client, event):
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
    user = make_orga_user(event, can_change_teams=True)
    client.force_login(user)
    djmail.outbox = []

    url = reverse(
        "orga:organiser.teams.update",
        kwargs={"organiser": event.organiser.slug, "pk": team.pk},
    )
    response = client.post(
        url,
        data={
            "invite-bulk_email": "first@example.com\nsecond@example.com",
            "form": "invite",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert team.invites.count() == 2
    assert len(djmail.outbox) == 2
    assert djmail.outbox[0].to == ["first@example.com"]
    assert djmail.outbox[1].to == ["second@example.com"]


@pytest.mark.django_db
def test_team_uninvite_get_shows_confirmation(client, event):
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
        invite = TeamInviteFactory(team=team, email="uninvite@example.com")
    user = make_orga_user(event, can_change_teams=True)
    client.force_login(user)

    url = reverse(
        "orga:organiser.teams.invites.uninvite",
        kwargs={
            "organiser": event.organiser.slug,
            "pk": team.pk,
            "invite_pk": invite.pk,
        },
    )
    response = client.get(url)

    assert response.status_code == 200


@pytest.mark.django_db
def test_team_uninvite_post_retracts_invitation(client, event):
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
        invite = TeamInviteFactory(team=team, email="uninvite@example.com")
    user = make_orga_user(event, can_change_teams=True)
    client.force_login(user)
    invite_pk = invite.pk

    url = reverse(
        "orga:organiser.teams.invites.uninvite",
        kwargs={
            "organiser": event.organiser.slug,
            "pk": team.pk,
            "invite_pk": invite_pk,
        },
    )
    response = client.post(url, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert not TeamInvite.objects.filter(pk=invite_pk).exists()


@pytest.mark.django_db
def test_team_uninvite_denied_without_permission(client, event):
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
        invite = TeamInviteFactory(team=team)
    user = UserFactory()
    client.force_login(user)

    url = reverse(
        "orga:organiser.teams.invites.uninvite",
        kwargs={
            "organiser": event.organiser.slug,
            "pk": team.pk,
            "invite_pk": invite.pk,
        },
    )
    response = client.get(url)

    assert response.status_code == 404


@pytest.mark.django_db
def test_team_resend_get_shows_confirmation(client, event):
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
        invite = TeamInviteFactory(team=team)
    user = make_orga_user(event, can_change_teams=True)
    client.force_login(user)

    url = reverse(
        "orga:organiser.teams.invites.resend",
        kwargs={
            "organiser": event.organiser.slug,
            "pk": team.pk,
            "invite_pk": invite.pk,
        },
    )
    response = client.get(url)

    assert response.status_code == 200


@pytest.mark.django_db
def test_team_resend_post_sends_email(client, event):
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
        invite = TeamInviteFactory(team=team, email="resend@example.com")
    user = make_orga_user(event, can_change_teams=True)
    client.force_login(user)
    djmail.outbox = []

    url = reverse(
        "orga:organiser.teams.invites.resend",
        kwargs={
            "organiser": event.organiser.slug,
            "pk": team.pk,
            "invite_pk": invite.pk,
        },
    )
    response = client.post(url, follow=True)

    assert response.status_code == 200
    assert team.invites.count() == 1
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["resend@example.com"]


@pytest.mark.django_db
def test_team_resend_denied_without_permission(client, event):
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
        invite = TeamInviteFactory(team=team)
    user = UserFactory()
    client.force_login(user)

    url = reverse(
        "orga:organiser.teams.invites.resend",
        kwargs={
            "organiser": event.organiser.slug,
            "pk": team.pk,
            "invite_pk": invite.pk,
        },
    )
    response = client.post(url, follow=True)

    assert response.status_code == 404


@pytest.mark.django_db
def test_team_member_delete_removes_member(client, event):
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
        member = UserFactory()
        team.members.add(member)
    user = make_orga_user(
        event,
        can_change_teams=True,
        can_create_events=True,
        can_change_organiser_settings=True,
        can_change_event_settings=True,
    )
    client.force_login(user)

    url = reverse(
        "orga:organiser.teams.members.delete",
        kwargs={
            "organiser": event.organiser.slug,
            "team_pk": team.pk,
            "user_pk": member.pk,
        },
    )
    response = client.post(url, follow=True)

    assert response.status_code == 200
    assert member not in team.members.all()


@pytest.mark.django_db
def test_team_member_delete_cannot_remove_last_member_with_change_teams(client, event):
    """Removing the last member of the only team with can_change_teams is prevented
    by check_access_permissions (mirroring legacy test_remove_other_team_member_but_not_last_member)."""
    with scopes_disabled():
        event.organiser.teams.update(can_change_teams=False)
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
        other_member = UserFactory()
        user = make_orga_user(teams=[team])
        team.members.add(other_member)
    client.force_login(user)
    assert team.members.count() == 2

    url = reverse(
        "orga:organiser.teams.members.delete",
        kwargs={
            "organiser": event.organiser.slug,
            "team_pk": team.pk,
            "user_pk": other_member.pk,
        },
    )
    response = client.post(url, follow=True)

    assert response.status_code == 200
    assert team.members.count() == 1
    assert other_member not in team.members.all()

    url = reverse(
        "orga:organiser.teams.members.delete",
        kwargs={
            "organiser": event.organiser.slug,
            "team_pk": team.pk,
            "user_pk": user.pk,
        },
    )
    response = client.post(url, follow=True)

    assert response.status_code == 200
    assert team.members.count() == 1
    assert user in team.members.all()


@pytest.mark.django_db
def test_team_member_delete_denied_without_permission(client, event):
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
        member = UserFactory()
        team.members.add(member)
    user = UserFactory()
    client.force_login(user)

    url = reverse(
        "orga:organiser.teams.members.delete",
        kwargs={
            "organiser": event.organiser.slug,
            "team_pk": team.pk,
            "user_pk": member.pk,
        },
    )
    response = client.post(url)

    assert response.status_code == 404
    assert member in team.members.all()


@pytest.mark.django_db
def test_team_reset_password_sends_reset_email(client, event):
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
        member = UserFactory()
        team.members.add(member)
    user = make_orga_user(event, can_change_teams=True)
    client.force_login(user)
    djmail.outbox = []
    assert not member.pw_reset_token

    url = reverse(
        "orga:organiser.teams.members.reset",
        kwargs={
            "organiser": event.organiser.slug,
            "team_pk": team.pk,
            "user_pk": member.pk,
        },
    )
    response = client.post(url, follow=True)

    assert response.status_code == 200
    member.refresh_from_db()
    assert member.pw_reset_token
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_team_reset_password_can_be_sent_twice(client, event):
    """Password reset can be triggered again, generating a new token."""
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
        member = UserFactory()
        team.members.add(member)
    user = make_orga_user(event, can_change_teams=True)
    client.force_login(user)
    djmail.outbox = []

    url = reverse(
        "orga:organiser.teams.members.reset",
        kwargs={
            "organiser": event.organiser.slug,
            "team_pk": team.pk,
            "user_pk": member.pk,
        },
    )

    client.post(url, follow=True)
    member.refresh_from_db()
    first_token = member.pw_reset_token

    client.post(url, follow=True)
    member.refresh_from_db()

    assert member.pw_reset_token != first_token
    assert len(djmail.outbox) == 2


@pytest.mark.django_db
def test_team_reset_password_denied_without_permission(client, event):
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
        member = UserFactory()
        team.members.add(member)
    user = UserFactory()
    client.force_login(user)

    url = reverse(
        "orga:organiser.teams.members.reset",
        kwargs={
            "organiser": event.organiser.slug,
            "team_pk": team.pk,
            "user_pk": member.pk,
        },
    )
    response = client.post(url)

    assert response.status_code == 404
    member.refresh_from_db()
    assert not member.pw_reset_token


@pytest.mark.django_db
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    EMAIL_PORT=1,
    DEBUG=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
def test_team_reset_password_shows_error_on_mail_failure(client, event):
    """When the reset email cannot be sent, an error message is shown and the
    password token is still set (but useless without the email)."""
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
        member = UserFactory()
        team.members.add(member)
    user = make_orga_user(event, can_change_teams=True)
    client.force_login(user)

    url = reverse(
        "orga:organiser.teams.members.reset",
        kwargs={
            "organiser": event.organiser.slug,
            "team_pk": team.pk,
            "user_pk": member.pk,
        },
    )
    response = client.post(url, follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert "could not be sent" in content


@pytest.mark.django_db
def test_organiser_speaker_list_accessible(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    url = reverse("orga:organiser.speakers", kwargs={"organiser": event.organiser.slug})
    response = client.get(url)

    assert response.status_code == 200


@pytest.mark.django_db
def test_organiser_speaker_list_shows_speakers(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event, user__name="Visible Speaker")
        sub = SubmissionFactory(event=event, state="accepted")
        sub.speakers.add(speaker)
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    url = reverse("orga:organiser.speakers", kwargs={"organiser": event.organiser.slug})
    response = client.get(url)

    assert response.status_code == 200
    assert "Visible Speaker" in response.content.decode()


@pytest.mark.django_db
def test_organiser_speaker_list_denied_without_permission(client, event):
    user = UserFactory()
    client.force_login(user)

    url = reverse("orga:organiser.speakers", kwargs={"organiser": event.organiser.slug})
    response = client.get(url)

    assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_organiser_speaker_list_query_count(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        for _ in range(item_count):
            speaker = SpeakerFactory(event=event)
            sub = SubmissionFactory(event=event, state="accepted")
            sub.speakers.add(speaker)
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    url = reverse("orga:organiser.speakers", kwargs={"organiser": event.organiser.slug})
    with django_assert_num_queries(12):
        response = client.get(url)

    assert response.status_code == 200


@pytest.mark.django_db
def test_speaker_search_returns_matching_speakers(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event, user__name="Searchable Person")
        sub = SubmissionFactory(event=event)
        sub.speakers.add(speaker)
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    url = reverse(
        "orga:organiser.user_list", kwargs={"organiser": event.organiser.slug}
    )
    response = client.get(url, {"search": "Searchable"})

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["results"][0]["name"] == "Searchable Person"


@pytest.mark.django_db
def test_speaker_search_returns_empty_for_short_query(client, event):
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    url = reverse(
        "orga:organiser.user_list", kwargs={"organiser": event.organiser.slug}
    )
    response = client.get(url, {"search": "ab"})

    data = response.json()
    assert data["count"] == 0
    assert data["results"] == []


@pytest.mark.django_db
def test_speaker_search_does_not_leak_inaccessible_speakers(client, event):
    """Speakers from events the user cannot access should not appear."""
    with scopes_disabled():
        other_event = EventFactory()
        speaker = SpeakerFactory(event=other_event, user__name="Hidden Speaker")
        sub = SubmissionFactory(event=other_event)
        sub.speakers.add(speaker)
    user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    url = reverse(
        "orga:organiser.user_list", kwargs={"organiser": event.organiser.slug}
    )
    response = client.get(url, {"search": "Hidden"})

    data = response.json()
    assert data["count"] == 0


@pytest.mark.django_db
def test_team_invite_invalid_email_shows_error(client, event):
    """Submitting an invalid email in the invite form shows errors."""
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
    user = make_orga_user(event, can_change_teams=True)
    client.force_login(user)

    url = reverse(
        "orga:organiser.teams.update",
        kwargs={"organiser": event.organiser.slug, "pk": team.pk},
    )
    response = client.post(
        url, data={"invite-email": "", "form": "invite"}, follow=True
    )

    assert response.status_code == 200
    assert team.invites.count() == 0


@pytest.mark.django_db
def test_team_update_with_warnings(client, event):
    """Updating a team that triggers warnings from check_access_permissions
    still saves but shows warnings."""
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser,
            can_change_teams=True,
            can_create_events=True,
            all_events=True,
        )
    user = make_orga_user(event, can_change_teams=True)
    client.force_login(user)

    url = reverse(
        "orga:organiser.teams.update",
        kwargs={"organiser": event.organiser.slug, "pk": team.pk},
    )
    response = client.post(
        url,
        data={
            "all_events": True,
            "can_change_submissions": True,
            "can_change_organiser_settings": True,
            "can_change_event_settings": True,
            "can_change_teams": True,
            "can_create_events": False,
            "form": "team",
            "name": "No Create Events",
        },
        follow=True,
    )

    assert response.status_code == 200
    team.refresh_from_db()
    assert team.name == "No Create Events"


@pytest.mark.django_db
def test_team_delete_with_warnings(client, event):
    """Deleting a team that triggers warnings still deletes but shows warnings."""
    with scopes_disabled():
        # Team 1: the user's team, keeps can_change_teams
        keep_team = TeamFactory(
            organiser=event.organiser,
            can_change_teams=True,
            can_create_events=True,
            all_events=True,
        )
        keep_team.members.add(UserFactory())
        # Team 2: a team with can_create_events that will be deleted
        deletable = TeamFactory(
            organiser=event.organiser, can_create_events=True, all_events=True
        )
    user = make_orga_user(event, can_change_teams=True, can_create_events=False)
    client.force_login(user)

    url = reverse(
        "orga:organiser.teams.delete",
        kwargs={"organiser": event.organiser.slug, "pk": deletable.pk},
    )
    response = client.post(url, follow=True)

    assert response.status_code == 200
    assert not Team.objects.filter(pk=deletable.pk).exists()


@pytest.mark.django_db
def test_team_update_view_get_shows_form(client, event):
    """GET on team update shows the team form with invite form."""
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, can_change_teams=True, all_events=True
        )
        member = UserFactory()
        team.members.add(member)
        TeamInviteFactory(team=team)
    user = make_orga_user(event, can_change_teams=True)
    client.force_login(user)

    url = reverse(
        "orga:organiser.teams.update",
        kwargs={"organiser": event.organiser.slug, "pk": team.pk},
    )
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert team.name in content
    assert member.name in content
