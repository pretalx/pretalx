# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
import json

import pytest
from django.core import mail as djmail
from django.urls import reverse
from django.utils.timezone import now as tz_now
from django_scopes import scopes_disabled

from pretalx.api.versions import CURRENT_VERSION
from pretalx.common.domain.queries.log import actions_by
from pretalx.person.domain.verification import (
    KIND_CHANGE,
    InvalidVerificationTokenError,
    make_verification_token,
    parse_verification_token,
)
from pretalx.person.models import User
from pretalx.person.models.auth_token import UserApiToken
from tests.factories import EventFactory, UserApiTokenFactory, UserFactory
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_user_settings_profile_and_password_forms(client, event):
    url = reverse("orga:user.view")
    user = make_orga_user(event)
    token = UserApiTokenFactory(user=user, name="Prod token")

    response = client.get(url)

    assert response.status_code == 302
    assert response.url == f"/orga/login/?next={url}"

    client.force_login(user)
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert f'value="{user.name}"' in content
    assert f'value="{user.email}"' in content
    assert token.name in content

    response = client.post(url, {"form": "nonexistent"}, follow=True)

    assert response.status_code == 200
    assert "trouble saving your input" in response.content.decode()

    response = client.post(
        url, {"form": "profile", "name": "Updated Name", "locale": "en"}
    )

    assert response.status_code == 302
    assert response.url == url
    user.refresh_from_db()
    assert user.name == "Updated Name"

    login_data = {
        "form": "login",
        "old_password": "wrongpassword1!",
        "password": "newpassword1!",
        "password_repeat": "newpassword1!",
        "email": user.email,
    }
    response = client.post(url, login_data, follow=True)

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.check_password("testpassword!")

    response = client.post(url, {**login_data, "old_password": "testpassword!"})

    assert response.status_code == 302
    assert response.url == url
    user.refresh_from_db()
    assert user.check_password("newpassword1!")


def test_user_settings_email_change_is_deferred_until_confirmed_or_cancelled(client):
    url = reverse("orga:user.view")
    user = UserFactory(email="old@example.com")
    client.force_login(user)
    djmail.outbox = []

    response = client.post(
        url,
        {
            "form": "login",
            "old_password": "testpassword!",
            "password": "",
            "password_repeat": "",
            "email": "new@example.com",
        },
        follow=True,
    )

    user.refresh_from_db()
    assert user.email == "old@example.com"
    assert user.pending_email == "new@example.com"
    assert len(djmail.outbox) == 2
    assert djmail.outbox[0].to == ["new@example.com"]
    assert djmail.outbox[1].to == ["old@example.com"]
    content = response.content.decode()
    assert "new@example.com" in content
    assert "confirmation link" in content
    assert "awaiting confirmation" in content
    assert 'value="cancel_email_change"' in content

    User.objects.filter(pk=user.pk).update(
        pending_email_sent=tz_now() - dt.timedelta(hours=25)
    )
    response = client.get(url)

    content = response.content.decode()
    assert "new@example.com" in content
    assert "expired" in content
    assert 'value="cancel_email_change"' in content
    user.refresh_from_db()
    assert user.pending_email == "new@example.com"
    assert user.pending_email_sent is not None

    token = make_verification_token(user, KIND_CHANGE)
    response = client.post(url, {"form": "cancel_email_change"})

    assert response.status_code == 302
    user.refresh_from_db()
    assert user.pending_email is None
    assert user.pending_email_sent is None
    with scopes_disabled():
        action = (
            actions_by(user)
            .filter(action_type="pretalx.user.email.change.cancel")
            .get()
        )
    assert action.data == {"pending_email": "new@example.com"}
    with pytest.raises(InvalidVerificationTokenError):
        parse_verification_token(token)


def test_user_settings_token_create_revoke_and_upgrade(client, event):
    url = reverse("orga:user.view")
    user = make_orga_user(event)
    client.force_login(user)

    response = client.post(
        url,
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
        log_entry = (
            token.logged_actions().filter(action_type="pretalx.user.token.create").get()
        )
    assert log_entry.person == user

    response = client.post(
        url,
        {
            "form": "token",
            "name": "All Events Token",
            "all_events": "on",
            "permission_preset": "read",
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        all_events_token = UserApiToken.objects.get(user=user, name="All Events Token")
        assert all_events_token.all_events is True
        assert not all_events_token.limit_events.exists()

    response = client.post(url, {"revoke": token.pk})

    assert response.status_code == 302
    token.refresh_from_db()
    assert not token.is_active

    old_token = UserApiTokenFactory(user=user, version="v1")
    response = client.post(url, {"tokenupgrade": old_token.pk})

    assert response.status_code == 302
    old_token.refresh_from_db()
    assert old_token.version == CURRENT_VERSION

    for data in ({"tokenupgrade": 99999}, {"revoke": 99999}):
        response = client.post(url, data)
        assert response.status_code == 302, data
        assert response.url == url, data


def test_user_settings_token_edit_logs_event_changes(client, event):
    user = make_orga_user(event)
    client.force_login(user)
    with scopes_disabled():
        second_event = EventFactory(organiser=event.organiser)
    token = UserApiTokenFactory(
        user=user, limit_events=[event], endpoints={"events": ["list"]}
    )
    url = reverse("orga:user.token.edit", kwargs={"pk": token.pk})

    def update_logs():
        with scopes_disabled():
            return list(
                token.logged_actions()
                .filter(action_type="pretalx.user.token.update")
                .order_by("pk")
            )

    response = client.get(url)
    assert response.status_code == 200

    response = client.post(url, {"limit_events": [event.pk]}, follow=True)

    assert response.status_code == 200
    assert update_logs() == []

    response = client.post(
        url, {"limit_events": [event.pk, second_event.pk]}, follow=True
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert set(token.limit_events.all()) == {event, second_event}
    (log_entry,) = update_logs()
    changes = log_entry.data["changes"]
    assert changes["limit_events"]["old"] == [event.pk]
    assert set(changes["limit_events"]["new"]) == {event.pk, second_event.pk}

    response = client.post(url, {"all_events": "on"}, follow=True)

    assert response.status_code == 200
    token.refresh_from_db()
    assert token.all_events is True
    _, log_entry = update_logs()
    changes = log_entry.data["changes"]
    assert changes["all_events"] == {"old": False, "new": True}
    assert changes["limit_events"]["old"] == [event.pk, second_event.pk]
    assert changes["limit_events"]["new"] == []


def test_user_settings_token_edit_denied_for_foreign_or_expired_token(client, event):
    user = make_orga_user(event)
    client.force_login(user)
    other_token = UserApiTokenFactory(endpoints={"events": ["list"]})
    expired_token = UserApiTokenFactory(
        user=user,
        limit_events=[event],
        endpoints={"events": ["list"]},
        expires=tz_now() - dt.timedelta(days=1),
    )

    for token in (other_token, expired_token):
        response = client.get(reverse("orga:user.token.edit", kwargs={"pk": token.pk}))
        assert response.status_code == 404, token


def test_subuser_view_demotes_superuser_and_respects_next_url(client):
    user = UserFactory(is_superuser=True)
    client.force_login(user)

    response = client.post(reverse("orga:user.subuser") + "?next=/orga/")

    assert response.status_code == 302
    assert response.url == "/orga/"
    user.refresh_from_db()
    assert not user.is_superuser
    assert user.is_administrator

    response = client.post(reverse("orga:user.subuser") + "?next=https://evil.com")

    assert response.status_code == 302
    assert response.url == "/orga/event/"

    plain_user = UserFactory()
    client.force_login(plain_user)
    response = client.post(reverse("orga:user.subuser"))

    assert response.status_code == 302
    plain_user.refresh_from_db()
    assert not plain_user.is_superuser
    assert not plain_user.is_administrator


def test_preferences_view_stores_table_preferences(client, event):
    url = reverse("orga:preferences", kwargs={"event": event.slug})

    user = make_orga_user(event)

    def post(payload):
        return client.post(url, data=payload, content_type="application/json")

    def preferences():
        return User.objects.get(pk=user.pk).get_event_preferences(event)

    client.force_login(UserFactory())

    assert post(json.dumps({"table_name": "submissions"})).status_code == 404

    client.force_login(user)

    response = post(
        json.dumps({"table_name": "submissions", "columns": ["title", "state"]})
    )

    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert preferences().get("tables.submissions.columns") == ["title", "state"]

    response = post(json.dumps({"table_name": "submissions", "ordering": ["-created"]}))

    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert preferences().get("tables.submissions.ordering") == ["-created"]

    response = post(json.dumps({"table_name": "submissions", "ordering": []}))

    assert response.status_code == 200
    assert preferences().get("tables.submissions.columns") == ["title", "state"]
    assert preferences().get("tables.submissions.ordering") is None

    response = post(json.dumps({"table_name": "submissions", "reset": True}))

    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert preferences().get("tables.submissions.columns") is None
    assert preferences().get("tables.submissions.ordering") is None

    for payload, error in (
        (json.dumps({}), "table_name is required"),
        ("not json", "Invalid JSON"),
        (
            json.dumps({"table_name": "submissions", "columns": "not_a_list"}),
            "columns must be a list",
        ),
        (
            json.dumps({"table_name": "submissions", "ordering": "not_a_list"}),
            "ordering must be a list",
        ),
    ):
        response = post(payload)
        assert response.status_code == 400, payload
        assert response.json() == {"error": error}, payload
