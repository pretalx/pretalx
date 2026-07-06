# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
import json

import pytest
from django.urls import reverse
from django.utils.timezone import now as tz_now
from django_scopes import scopes_disabled

from pretalx.api.versions import CURRENT_VERSION
from pretalx.person.interfaces.forms import (
    AuthTokenForm,
    LoginInfoForm,
    OrgaProfileForm,
)
from pretalx.person.models.auth_token import UserApiToken
from tests.factories import EventFactory, UserApiTokenFactory, UserFactory
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_user_settings_get_requires_login(client):
    response = client.get(reverse("orga:user.view"))

    assert response.status_code == 302
    assert "/login" in response.url


def test_user_settings_get_renders_for_authenticated_user(client):
    user = UserFactory()
    client.force_login(user)

    response = client.get(reverse("orga:user.view"))

    assert response.status_code == 200
    assert isinstance(response.context["login_form"], LoginInfoForm)
    assert isinstance(response.context["profile_form"], OrgaProfileForm)
    assert isinstance(response.context["token_form"], AuthTokenForm)


def test_user_settings_post_profile_updates_name(client):
    user = UserFactory()
    client.force_login(user)

    response = client.post(
        reverse("orga:user.view"),
        {"form": "profile", "name": "Updated Name", "locale": "en"},
    )

    assert response.status_code == 302
    assert response.url == reverse("orga:user.view")
    user.refresh_from_db()
    assert user.name == "Updated Name"


def test_user_settings_post_login_changes_password(client):
    user = UserFactory(password="oldpassword1!")
    client.force_login(user)

    response = client.post(
        reverse("orga:user.view"),
        {
            "form": "login",
            "old_password": "oldpassword1!",
            "password": "newpassword1!",
            "password_repeat": "newpassword1!",
            "email": user.email,
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("orga:user.view")
    user.refresh_from_db()
    assert user.check_password("newpassword1!")


def test_user_settings_post_login_wrong_old_password_fails(client):
    user = UserFactory(password="correctpassword1!")
    client.force_login(user)

    response = client.post(
        reverse("orga:user.view"),
        {
            "form": "login",
            "old_password": "wrongpassword1!",
            "password": "newpassword1!",
            "password_repeat": "newpassword1!",
            "email": user.email,
        },
        follow=True,
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.check_password("correctpassword1!")


def test_user_settings_post_token_creates_api_token(client, event):
    user = make_orga_user(event)
    client.force_login(user)

    response = client.post(
        reverse("orga:user.view"),
        {
            "form": "token",
            "name": "My Token",
            "limit_events": [event.pk],
            "permission_preset": "read",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        token = UserApiToken.objects.get(user=user)
    assert token.name == "My Token"
    assert set(token.limit_events.all()) == {event}
    assert token.all_events is False


def test_user_settings_post_token_creates_all_events_token(client, event):
    user = make_orga_user(event)
    client.force_login(user)

    response = client.post(
        reverse("orga:user.view"),
        {
            "form": "token",
            "name": "My Token",
            "all_events": "on",
            "permission_preset": "read",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        token = UserApiToken.objects.get(user=user)
    assert token.all_events is True
    assert not token.limit_events.exists()


def test_user_settings_token_edit_adds_event(client, event):
    user = make_orga_user(event)
    client.force_login(user)
    with scopes_disabled():
        second_event = EventFactory(organiser=event.organiser)
    token = UserApiTokenFactory(
        user=user, limit_events=[event], endpoints={"events": ["list"]}
    )
    url = reverse("orga:user.token.edit", kwargs={"pk": token.pk})

    response = client.get(url)
    assert response.status_code == 200

    response = client.post(
        url, {"limit_events": [event.pk, second_event.pk]}, follow=True
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert set(token.limit_events.all()) == {event, second_event}
        log_entry = (
            user.logged_actions()
            .filter(action_type="pretalx.user.token.update")
            .first()
        )
        assert log_entry
        changes = log_entry.data["changes"]
        assert changes["limit_events"]["old"] == [event.pk]
        assert set(changes["limit_events"]["new"]) == {event.pk, second_event.pk}


def test_user_settings_token_edit_switches_to_all_events(client, event):
    user = make_orga_user(event)
    client.force_login(user)
    token = UserApiTokenFactory(
        user=user, limit_events=[event], endpoints={"events": ["list"]}
    )

    response = client.post(
        reverse("orga:user.token.edit", kwargs={"pk": token.pk}),
        {"all_events": "on"},
        follow=True,
    )

    assert response.status_code == 200
    token.refresh_from_db()
    assert token.all_events is True
    with scopes_disabled():
        log_entry = (
            user.logged_actions()
            .filter(action_type="pretalx.user.token.update")
            .first()
        )
        assert log_entry
        changes = log_entry.data["changes"]
        assert changes["all_events"] == {"old": False, "new": True}
        assert changes["limit_events"] == {"old": [event.pk], "new": []}


def test_user_settings_token_edit_without_changes_does_not_log(client, event):
    user = make_orga_user(event)
    client.force_login(user)
    token = UserApiTokenFactory(
        user=user, limit_events=[event], endpoints={"events": ["list"]}
    )

    response = client.post(
        reverse("orga:user.token.edit", kwargs={"pk": token.pk}),
        {"limit_events": [event.pk]},
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert (
            not user.logged_actions()
            .filter(action_type="pretalx.user.token.update")
            .exists()
        )


def test_user_settings_token_edit_denied_for_other_users_token(client, event):
    user = make_orga_user(event)
    client.force_login(user)
    other_token = UserApiTokenFactory(endpoints={"events": ["list"]})

    response = client.get(
        reverse("orga:user.token.edit", kwargs={"pk": other_token.pk})
    )

    assert response.status_code == 404


def test_user_settings_token_edit_denied_for_expired_token(client, event):
    user = make_orga_user(event)
    client.force_login(user)
    token = UserApiTokenFactory(
        user=user,
        limit_events=[event],
        endpoints={"events": ["list"]},
        expires=tz_now() - dt.timedelta(days=1),
    )

    response = client.get(reverse("orga:user.token.edit", kwargs={"pk": token.pk}))

    assert response.status_code == 404


def test_user_settings_post_token_revoke(client):
    user = UserFactory()
    client.force_login(user)
    token = UserApiTokenFactory(user=user)

    response = client.post(reverse("orga:user.view"), {"revoke": token.pk})

    assert response.status_code == 302
    token.refresh_from_db()
    assert not token.is_active


def test_user_settings_post_token_upgrade(client):
    user = UserFactory()
    client.force_login(user)
    token = UserApiTokenFactory(user=user, version="LEGACY")

    response = client.post(reverse("orga:user.view"), {"tokenupgrade": token.pk})

    assert response.status_code == 302
    token.refresh_from_db()
    assert token.version == CURRENT_VERSION


def test_user_settings_post_upgrade_nonexistent_token_redirects(client):
    user = UserFactory()
    client.force_login(user)

    response = client.post(reverse("orga:user.view"), {"tokenupgrade": 99999})

    assert response.status_code == 302
    assert response.url == reverse("orga:user.view")


def test_user_settings_post_invalid_form_shows_error(client):
    user = UserFactory()
    client.force_login(user)

    response = client.post(
        reverse("orga:user.view"), {"form": "nonexistent"}, follow=True
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "trouble saving your input" in content


def test_user_settings_post_revoke_nonexistent_token_redirects(client):
    user = UserFactory()
    client.force_login(user)

    response = client.post(reverse("orga:user.view"), {"revoke": 99999})

    assert response.status_code == 302
    assert response.url == reverse("orga:user.view")


def test_subuser_view_demotes_superuser(client):
    user = UserFactory(is_superuser=True)
    client.force_login(user)

    response = client.post(reverse("orga:user.subuser"))

    assert response.status_code == 302
    user.refresh_from_db()
    assert not user.is_superuser
    assert user.is_administrator


@pytest.mark.parametrize(
    ("next_url", "expected_redirect"),
    (("/orga/", "/orga/"), ("https://evil.com", "/orga/event/")),
    ids=["valid_next", "external_next_rejected"],
)
def test_subuser_view_respects_next_url(client, next_url, expected_redirect):
    user = UserFactory(is_superuser=True)
    client.force_login(user)

    response = client.post(reverse("orga:user.subuser") + f"?next={next_url}")

    assert response.status_code == 302
    assert response.url == expected_redirect


def test_subuser_view_non_superuser_still_works(client):
    user = UserFactory()
    client.force_login(user)

    response = client.post(reverse("orga:user.subuser"))

    assert response.status_code == 302
    user.refresh_from_db()
    assert not user.is_superuser
    assert not user.is_administrator


@pytest.fixture
def preferences_url(event):
    return reverse("orga:preferences", kwargs={"event": event.slug})


def test_preferences_view_requires_event_permission(client, event, preferences_url):
    user = UserFactory()
    client.force_login(user)

    response = client.post(
        preferences_url,
        data=json.dumps({"table_name": "submissions"}),
        content_type="application/json",
    )

    assert response.status_code == 404


def test_preferences_view_set_columns(client, event, preferences_url):
    user = make_orga_user(event)
    client.force_login(user)

    response = client.post(
        preferences_url,
        data=json.dumps({"table_name": "submissions", "columns": ["title", "state"]}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json() == {"success": True}
    preferences = user.get_event_preferences(event)
    assert preferences.get("tables.submissions.columns") == ["title", "state"]


def test_preferences_view_set_ordering(client, event, preferences_url):
    user = make_orga_user(event)
    client.force_login(user)

    response = client.post(
        preferences_url,
        data=json.dumps({"table_name": "submissions", "ordering": ["-created"]}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json() == {"success": True}
    preferences = user.get_event_preferences(event)
    assert preferences.get("tables.submissions.ordering") == ["-created"]


def test_preferences_view_clear_ordering_with_empty_list(
    client, event, preferences_url
):
    """Sending an empty ordering list clears the ordering preference."""
    user = make_orga_user(event)
    client.force_login(user)

    client.post(
        preferences_url,
        data=json.dumps({"table_name": "submissions", "ordering": ["-created"]}),
        content_type="application/json",
    )

    response = client.post(
        preferences_url,
        data=json.dumps({"table_name": "submissions", "ordering": []}),
        content_type="application/json",
    )

    assert response.status_code == 200
    preferences = user.get_event_preferences(event)
    assert preferences.get("tables.submissions.ordering") is None


def test_preferences_view_reset(client, event, preferences_url):
    """Reset clears both columns and ordering for a table."""
    user = make_orga_user(event)
    client.force_login(user)

    client.post(
        preferences_url,
        data=json.dumps(
            {
                "table_name": "submissions",
                "columns": ["title"],
                "ordering": ["-created"],
            }
        ),
        content_type="application/json",
    )

    response = client.post(
        preferences_url,
        data=json.dumps({"table_name": "submissions", "reset": True}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json() == {"success": True}
    preferences = user.get_event_preferences(event)
    assert preferences.get("tables.submissions.columns") is None
    assert preferences.get("tables.submissions.ordering") is None


def test_preferences_view_missing_table_name(client, event, preferences_url):
    user = make_orga_user(event)
    client.force_login(user)

    response = client.post(
        preferences_url, data=json.dumps({}), content_type="application/json"
    )

    assert response.status_code == 400
    assert response.json()["error"] == "table_name is required"


def test_preferences_view_invalid_json(client, event, preferences_url):
    user = make_orga_user(event)
    client.force_login(user)

    response = client.post(
        preferences_url, data="not json", content_type="application/json"
    )

    assert response.status_code == 400
    assert response.json()["error"] == "Invalid JSON"


@pytest.mark.parametrize(
    ("field", "error_msg"),
    (("columns", "columns must be a list"), ("ordering", "ordering must be a list")),
)
def test_preferences_view_rejects_non_list_field(
    client, event, preferences_url, field, error_msg
):
    user = make_orga_user(event)
    client.force_login(user)

    response = client.post(
        preferences_url,
        data=json.dumps({"table_name": "submissions", field: "not_a_list"}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"] == error_msg
