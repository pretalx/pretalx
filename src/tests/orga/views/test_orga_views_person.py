# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import json

import pytest
from django.urls import reverse


@pytest.mark.parametrize(
    "search,orga_results",
    (
        ("a", 0),
        ("aa", 0),
        ("aaa", 0),
        ("Jane S", 1),
    ),
)
@pytest.mark.django_db
def test_user_typeahead(
    orga_client,
    event,
    speaker,
    submission,
    other_orga_user,
    search,
    orga_results,
):
    orga_response = orga_client.get(
        reverse("orga:organiser.user_list", kwargs={"organiser": event.organiser.slug}),
        data={"search": search, "orga": True},
        follow=True,
    )
    assert orga_response.status_code == 200
    orga_content = json.loads(orga_response.text)
    assert orga_content["count"] == orga_results
    if orga_results:
        assert "name" in orga_content["results"][0]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "follow,expected", (("/orga/", "/orga/"), ("https://example.com", "/orga/event/"))
)
def test_remove_superuser(orga_client, orga_user, follow, expected):
    orga_user.is_superuser = True
    orga_user.save()
    response = orga_client.get(
        reverse("orga:user.subuser"),
        data={"next": follow},
    )

    orga_user.refresh_from_db()
    assert response.status_code == 302
    assert response.url == expected
    assert not orga_user.is_superuser


@pytest.mark.django_db
def test_remove_superuser_if_no_superuser(orga_client, orga_user):
    response = orga_client.get(reverse("orga:user.subuser"), follow=True)

    orga_user.refresh_from_db()
    assert response.status_code == 200
    assert not orga_user.is_superuser


@pytest.mark.django_db
def test_orga_wrong_profile_page_update(orga_client, orga_user):
    response = orga_client.post(
        reverse("orga:user.view"), {"form": "tokennnnnn"}, follow=True
    )
    assert response.status_code == 200
    assert "trouble saving your input" in response.text


@pytest.mark.django_db
def test_orga_update_login_info(orga_client, orga_user):
    response = orga_client.post(
        reverse("orga:user.view"),
        {
            "form": "login",
            "old_password": "orgapassw0rd",
            "password": "tr4lalalala",
            "password_repeat": "tr4lalalala",
            "email": orga_user.email,
        },
        follow=True,
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_orga_update_profile_info(orga_client, orga_user):
    response = orga_client.post(
        reverse("orga:user.view"),
        {"form": "profile", "name": "New name", "locale": "en"},
        follow=True,
    )
    assert response.status_code == 200
    assert "have been saved" in response.text
    orga_user.refresh_from_db()
    assert orga_user.name == "New name"


@pytest.mark.django_db
def test_token_edit_view_accessible(orga_client, orga_user_token):
    """Test that the edit view is accessible for active tokens."""
    response = orga_client.get(
        reverse("orga:user.token.edit", kwargs={"pk": orga_user_token.pk})
    )
    assert response.status_code == 200
    assert orga_user_token.name in response.text


@pytest.mark.django_db
def test_token_edit_update_name(orga_client, orga_user_token):
    """Test updating the token name."""
    response = orga_client.post(
        reverse("orga:user.token.edit", kwargs={"pk": orga_user_token.pk}),
        {
            "name": "Updated Token Name",
            "events": [e.pk for e in orga_user_token.events.all()],
            "permission_preset": "read",
        },
        follow=True,
    )
    assert response.status_code == 200
    assert "has been updated" in response.text
    orga_user_token.refresh_from_db()
    assert orga_user_token.name == "Updated Token Name"


@pytest.mark.django_db
def test_token_edit_update_events(orga_client, orga_user_token, event, other_event):
    """Test updating token events."""
    # First verify current state
    current_events = list(orga_user_token.events.all())
    assert len(current_events) > 0

    # Update to just one event
    response = orga_client.post(
        reverse("orga:user.token.edit", kwargs={"pk": orga_user_token.pk}),
        {
            "name": orga_user_token.name,
            "events": [event.pk],
            "permission_preset": "read",
        },
        follow=True,
    )
    assert response.status_code == 200
    orga_user_token.refresh_from_db()
    assert list(orga_user_token.events.all()) == [event]


@pytest.mark.django_db
def test_token_edit_cannot_edit_expired(orga_client, orga_user_token):
    """Test that expired tokens cannot be edited."""
    from django.utils.timezone import now, timedelta

    orga_user_token.expires = now() - timedelta(days=1)
    orga_user_token.save()

    response = orga_client.get(
        reverse("orga:user.token.edit", kwargs={"pk": orga_user_token.pk}),
        follow=True,
    )
    assert response.status_code == 200
    # Should redirect to user settings with error
    assert "not found or already expired" in response.text


@pytest.mark.django_db
def test_token_edit_cannot_edit_other_user_token(orga_client, other_orga_user):
    """Test that users cannot edit tokens belonging to other users."""
    from pretalx.person.models.auth_token import UserApiToken

    other_token = UserApiToken.objects.create(name="other", user=other_orga_user)

    response = orga_client.get(
        reverse("orga:user.token.edit", kwargs={"pk": other_token.pk}),
        follow=True,
    )
    assert response.status_code == 200
    # Should redirect to user settings with error
    assert "not found or already expired" in response.text


@pytest.mark.django_db
def test_token_value_unchanged_after_edit(orga_client, orga_user_token):
    """Test that the token value is not changed when editing."""
    original_token = orga_user_token.token

    response = orga_client.post(
        reverse("orga:user.token.edit", kwargs={"pk": orga_user_token.pk}),
        {
            "name": "Changed Name",
            "events": [e.pk for e in orga_user_token.events.all()],
            "permission_preset": "write",
        },
        follow=True,
    )
    assert response.status_code == 200
    orga_user_token.refresh_from_db()
    assert orga_user_token.token == original_token


@pytest.mark.django_db
def test_token_edit_permission_preset_change(orga_client, orga_user_token):
    """Test changing permission preset from read to write."""
    from pretalx.person.models.auth_token import UserApiToken, WRITE_PERMISSIONS

    # Verify starting with read
    assert orga_user_token.permission_preset == "read"

    response = orga_client.post(
        reverse("orga:user.token.edit", kwargs={"pk": orga_user_token.pk}),
        {
            "name": orga_user_token.name,
            "events": [e.pk for e in orga_user_token.events.all()],
            "permission_preset": "write",
        },
        follow=True,
    )
    assert response.status_code == 200
    assert "has been updated" in response.text

    # Get a fresh instance to avoid cached_property issues
    updated_token = UserApiToken.objects.get(pk=orga_user_token.pk)
    assert updated_token.permission_preset == "write"
    # Verify all endpoints have write permissions
    for endpoint, perms in updated_token.endpoints.items():
        assert set(perms) == set(WRITE_PERMISSIONS)


@pytest.mark.django_db
def test_token_edit_requires_events(orga_client, orga_user_token):
    """Test that editing a token without events shows an error."""
    response = orga_client.post(
        reverse("orga:user.token.edit", kwargs={"pk": orga_user_token.pk}),
        {
            "name": orga_user_token.name,
            "events": [],
            "permission_preset": "read",
        },
    )
    assert response.status_code == 200
    # Form should not save and should show the edit page again
    assert "Edit API Token" in response.text
    # Check for error message (may be in invalid-feedback div)
    assert "at least one event" in response.text.lower() or "invalid-feedback" in response.text


@pytest.mark.django_db
def test_token_edit_rejects_past_expiration(orga_client, orga_user_token):
    """Test that editing a token with a past expiration date shows an error."""
    from django.utils.timezone import now, timedelta

    past_date = (now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    response = orga_client.post(
        reverse("orga:user.token.edit", kwargs={"pk": orga_user_token.pk}),
        {
            "name": orga_user_token.name,
            "events": [e.pk for e in orga_user_token.events.all()],
            "permission_preset": "read",
            "expires": past_date,
        },
    )
    assert response.status_code == 200
    # Form should not save and should show the edit page again
    assert "Edit API Token" in response.text
    # Check for error message
    assert "past" in response.text.lower() or "invalid-feedback" in response.text


@pytest.mark.django_db
def test_token_create_requires_events(orga_client):
    """Test that creating a token without events shows an error."""
    from pretalx.person.models.auth_token import UserApiToken

    initial_count = UserApiToken.objects.count()

    response = orga_client.post(
        reverse("orga:user.view"),
        {
            "form": "token",
            "name": "Test Token",
            "events": [],
            "permission_preset": "read",
        },
    )
    assert response.status_code == 200
    # Token should not be created
    assert UserApiToken.objects.count() == initial_count
    # Should show user settings page with form
    assert "Create new token" in response.text
