# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.conf import settings
from django.core import mail as djmail
from django.urls import reverse
from django.utils.module_loading import import_string
from django.utils.timezone import now

from tests.factories import EventFactory, UserFactory

SessionStore = import_string(f"{settings.SESSION_ENGINE}.SessionStore")

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_login_view_successful_login(client, event):
    UserFactory(email="speaker@example.com", password="testpassword!")
    url = reverse("cfp:event.login", kwargs={"event": event.slug})

    response = client.post(
        url, {"login_email": "speaker@example.com", "login_password": "testpassword!"}
    )

    assert response.status_code == 302
    assert event.urls.user_submissions in response.url


def test_login_view_incorrect_password(client, event):
    UserFactory(email="speaker@example.com", password="testpassword!")
    url = reverse("cfp:event.login", kwargs={"event": event.slug})

    response = client.post(
        url, {"login_email": "speaker@example.com", "login_password": "wrongpassword!"}
    )

    assert response.status_code == 200
    assert response.context["form"].errors


def test_login_view_redirects_authenticated_user(client, event):
    speaker = UserFactory()
    client.force_login(speaker)
    url = reverse("cfp:event.login", kwargs={"event": event.slug})

    response = client.get(url)

    assert response.status_code == 302
    assert event.urls.user_submissions in response.url


def test_login_view_404_for_non_event(client):
    """Login page returns 404 when event is not public."""
    event = EventFactory(is_public=False)
    url = reverse("cfp:event.login", kwargs={"event": event.slug})

    response = client.get(url)

    assert response.status_code == 404


def test_logout_view_post_logs_out(client, event):
    """POST to logout clears the session and redirects to event start."""
    speaker = UserFactory()
    client.force_login(speaker)
    url = reverse("cfp:event.logout", kwargs={"event": event.slug})

    response = client.post(url)

    assert response.status_code == 302
    assert f"/{event.slug}/cfp" in response.url
    # Verify the user is actually logged out
    me_url = reverse("cfp:event.user.submissions", kwargs={"event": event.slug})
    me_response = client.get(me_url)
    # Logged-out user gets redirected to login
    assert me_response.status_code == 302


def test_reset_view_sends_reset_email(client, event):
    speaker = UserFactory(email="speaker@example.com")
    djmail.outbox = []
    url = reverse("cfp:event.reset", kwargs={"event": event.slug})

    response = client.post(url, {"login_email": "speaker@example.com"})

    assert response.status_code == 302
    speaker.refresh_from_db()
    assert speaker.pw_reset_token is not None
    assert len(djmail.outbox) == 1
    assert "speaker@example.com" in djmail.outbox[0].to


def test_reset_view_nonexistent_email_shows_success(client, event):
    """Posting a non-existent email still shows success message (no info leak)."""
    djmail.outbox = []
    url = reverse("cfp:event.reset", kwargs={"event": event.slug})

    response = client.post(url, {"login_email": "nobody@example.com"})

    assert response.status_code == 302
    assert len(djmail.outbox) == 0


def test_reset_view_blocks_repeated_reset_within_24h(client, event):
    speaker = UserFactory(
        email="speaker@example.com",
        pw_reset_token="oldtoken123",
        pw_reset_time=now() - dt.timedelta(hours=1),
    )
    djmail.outbox = []
    url = reverse("cfp:event.reset", kwargs={"event": event.slug})

    response = client.post(url, {"login_email": "speaker@example.com"})

    assert response.status_code == 302
    assert len(djmail.outbox) == 0
    speaker.refresh_from_db()
    assert speaker.pw_reset_token == "oldtoken123"


def test_recover_view_sets_new_password(client, event):
    speaker = UserFactory(pw_reset_token="validtoken123", pw_reset_time=now())
    url = reverse(
        "cfp:event.recover", kwargs={"event": event.slug, "token": "validtoken123"}
    )

    response = client.post(
        url,
        {"password": "newsecurepassword1!", "password_repeat": "newsecurepassword1!"},
    )

    assert response.status_code == 302
    assert "login" in response.url
    speaker.refresh_from_db()
    assert speaker.pw_reset_token is None
    assert speaker.check_password("newsecurepassword1!")


def test_recover_view_redirects_on_invalid_token(client, event):
    url = reverse(
        "cfp:event.recover", kwargs={"event": event.slug, "token": "bogustoken"}
    )

    response = client.get(url)

    assert response.status_code == 302
    assert "reset" in response.url


def test_recover_view_rejects_mismatched_passwords(client, event):
    """Mismatched passwords keep the token and don't reset the password."""
    speaker = UserFactory(pw_reset_token="validtoken123", pw_reset_time=now())
    url = reverse(
        "cfp:event.recover", kwargs={"event": event.slug, "token": "validtoken123"}
    )

    response = client.post(
        url,
        {"password": "newsecurepassword1!", "password_repeat": "differentpassword1!"},
    )

    assert response.status_code == 200
    speaker.refresh_from_db()
    assert speaker.pw_reset_token == "validtoken123"


def test_event_auth_post_valid_session_redirects_to_event_base(client, event):
    parent_store = SessionStore()
    parent_store["event_access"] = True
    parent_store.create()

    key = f"pretalx_event_access_{event.pk}"
    child_store = SessionStore()
    child_store[key] = parent_store.session_key
    child_store.create()

    url = reverse("cfp:event.auth", kwargs={"event": event.slug})
    response = client.post(url, {"session": child_store.session_key})

    assert response.status_code == 302
    assert response.url == event.urls.base


def test_event_auth_post_invalid_session_returns_403(client, event):
    url = reverse("cfp:event.auth", kwargs={"event": event.slug})

    response = client.post(url, {"session": "invalidsessionkey"})

    assert response.status_code == 403


def test_event_auth_post_missing_event_access_returns_403(client, event):
    """EventAuth returns 403 when parent session has no 'event_access' key."""
    parent_store = SessionStore()
    parent_store["something_else"] = True
    parent_store.create()

    key = f"pretalx_event_access_{event.pk}"
    child_store = SessionStore()
    child_store[key] = parent_store.session_key
    child_store.create()

    url = reverse("cfp:event.auth", kwargs={"event": event.slug})
    response = client.post(url, {"session": child_store.session_key})

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("target", "url_part"), (("cfp", "/cfp"), ("schedule", "/schedule/"))
)
def test_event_auth_post_target_redirects_correctly(client, event, target, url_part):
    parent_store = SessionStore()
    parent_store["event_access"] = True
    parent_store.create()

    key = f"pretalx_event_access_{event.pk}"
    child_store = SessionStore()
    child_store[key] = parent_store.session_key
    child_store.create()

    url = reverse("cfp:event.auth", kwargs={"event": event.slug})
    response = client.post(url, {"session": child_store.session_key, "target": target})

    assert response.status_code == 302
    assert url_part in response.url


def test_event_auth_post_unknown_target_redirects_to_base(client, event):
    parent_store = SessionStore()
    parent_store["event_access"] = True
    parent_store.create()

    key = f"pretalx_event_access_{event.pk}"
    child_store = SessionStore()
    child_store[key] = parent_store.session_key
    child_store.create()

    url = reverse("cfp:event.auth", kwargs={"event": event.slug})
    response = client.post(
        url, {"session": child_store.session_key, "target": "unknown"}
    )

    assert response.status_code == 302
    assert response.url == event.urls.base
