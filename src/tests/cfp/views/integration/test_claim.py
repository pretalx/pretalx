# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.urls import reverse
from django_scopes import scopes_disabled

from pretalx.person.models import SpeakerProfile, User
from tests.factories import SpeakerFactory, SpeakerRoleFactory, UserFactory

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def make_invited_profile(event, **kwargs):
    kwargs.setdefault("email", "invited@example.com")
    kwargs.setdefault("name", "Invited Speaker")
    return SpeakerFactory(
        event=event, user=None, invitation_token="claimtoken123", **kwargs
    )


def claim_url(event, token="claimtoken123"):
    return reverse("cfp:event.claim", kwargs={"event": event.slug, "token": token})


def test_claim_anonymous_sees_auth_form_and_profile_stays_unlinked(client, event):
    profile = make_invited_profile(event)

    response = client.get(claim_url(event))

    assert response.status_code == 200
    assert response.context["auth_form"] is not None
    profile.refresh_from_db()
    assert profile.user is None


def test_claim_anonymous_register_seeds_locale_and_returns_to_claim(client, event):
    profile = make_invited_profile(event, locale="de")

    response = client.post(
        claim_url(event),
        {
            "register_name": "New Account",
            "register_email": "invited@example.com",
            "register_password": "a-very-good-password!",
            "register_password_repeat": "a-very-good-password!",
        },
    )

    assert response.status_code == 302
    assert response.url == claim_url(event)
    user = User.objects.get(email="invited@example.com")
    # Accounts registered through the claim flow adopt the profile locale.
    assert user.locale == "de"
    profile.refresh_from_db()
    assert profile.user is None


def test_claim_confirm_page_shows_speaker_visible_data_only(client, event):
    profile = make_invited_profile(
        event,
        biography="A biography",
        internal_notes="Secret organiser notes",
        has_arrived=True,
    )
    client.force_login(UserFactory())

    response = client.get(claim_url(event))

    assert response.status_code == 200
    content = response.text
    assert "Invited Speaker" in content
    assert "A biography" in content
    assert "invited@example.com" in content
    assert "Secret organiser notes" not in content
    profile.refresh_from_db()
    assert profile.user is None


def test_claim_accept_links_profile_and_redirects_to_profile_edit(client, event):
    profile = make_invited_profile(event, locale="de")
    old_guid = profile.guid
    user = UserFactory(email="different-address@example.com", locale="en")
    client.force_login(user)

    response = client.post(claim_url(event))

    assert response.status_code == 302
    assert response.url == event.urls.user
    profile.refresh_from_db()
    # The claim link is a bearer credential: whoever is logged in claims,
    # regardless of the invited address.
    assert profile.user == user
    assert profile.invitation_token is None
    assert profile.guid == old_guid
    # Pre-existing accounts keep their locale; only claim-flow
    # registrations adopt the profile locale.
    user.refresh_from_db()
    assert user.locale == "en"


def test_claim_with_existing_profile_shows_merge_form(client, event):
    make_invited_profile(event)
    user = UserFactory()
    with scopes_disabled():
        user.get_speaker(event)
    client.force_login(user)

    response = client.get(claim_url(event))

    assert response.status_code == 200
    form = response.context["merge_form"]
    assert form is not None
    assert "name" in form.fields
    assert "email" in form.fields


def test_claim_merge_repoints_submission_and_deletes_managed_profile(client, event):
    profile = make_invited_profile(event)
    with scopes_disabled():
        role = SpeakerRoleFactory(submission__event=event, speaker=profile)
    user = UserFactory()
    with scopes_disabled():
        existing = user.get_speaker(event)
    client.force_login(user)

    response = client.post(claim_url(event), {"name": "merged", "email": "merged"})

    assert response.status_code == 302
    assert response.url == event.urls.user
    with scopes_disabled():
        assert not SpeakerProfile.objects.filter(pk=profile.pk).exists()
        role.refresh_from_db()
        assert role.speaker == existing
        existing.refresh_from_db()
        assert existing.name == "Invited Speaker"
        assert existing.email == "invited@example.com"


def test_claim_invalid_token_shows_error_and_modifies_nothing(client, event):
    profile = make_invited_profile(event)
    client.force_login(UserFactory())

    response = client.get(claim_url(event, token="wrongtoken"))

    assert response.status_code == 404
    assert response.context["claimed_profile"] is None
    profile.refresh_from_db()
    assert profile.user is None
    assert profile.invitation_token == "claimtoken123"


def test_claim_post_invalid_token_modifies_nothing(client, event):
    profile = make_invited_profile(event)
    client.force_login(UserFactory())

    response = client.post(claim_url(event, token="wrongtoken"))

    assert response.status_code == 404
    profile.refresh_from_db()
    assert profile.user is None


def test_old_pw_reset_invite_url_redirects_to_password_reset(client, event):
    response = client.get(f"/{event.slug}/invite/sometoken123")

    assert response.status_code == 302
    assert response.url == reverse(
        "cfp:event.recover", kwargs={"event": event.slug, "token": "sometoken123"}
    )


def test_claim_confirm_page_shows_locale_name(client, event):
    make_invited_profile(event, locale="en")
    client.force_login(UserFactory())

    response = client.get(claim_url(event))

    assert response.status_code == 200
    assert response.context["claimed_locale_name"] == "English"


def test_claim_anonymous_invalid_auth_form_rerenders(client, event):
    profile = make_invited_profile(event)

    response = client.post(claim_url(event), {"login_email": "nope"})

    assert response.status_code == 200
    assert response.context["auth_form"].errors
    profile.refresh_from_db()
    assert profile.user is None


def test_claim_anonymous_login_path_returns_to_claim(client, event):
    profile = make_invited_profile(event, locale="de")
    user = UserFactory(
        email="account@example.com", password="testpassword!", locale="en"
    )

    response = client.post(
        claim_url(event),
        {"login_email": "account@example.com", "login_password": "testpassword!"},
    )

    assert response.status_code == 302
    assert response.url == claim_url(event)
    user.refresh_from_db()
    # Logging in (as opposed to registering) never touches the locale.
    assert user.locale == "en"
    profile.refresh_from_db()
    assert profile.user is None


def test_claim_merge_form_invalid_rerenders(client, event):
    profile = make_invited_profile(event)
    user = UserFactory()
    with scopes_disabled():
        user.get_speaker(event)
    client.force_login(user)

    response = client.post(claim_url(event), {})

    assert response.status_code == 200
    assert response.context["merge_form"].errors
    with scopes_disabled():
        assert SpeakerProfile.objects.filter(pk=profile.pk).exists()
