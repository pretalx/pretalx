# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import time

import pytest
from django.contrib.auth import SESSION_KEY
from django.core import mail as djmail
from django.test import override_settings
from django.urls import reverse
from django.utils.timezone import now

from pretalx.person.enums import EmailVerificationState
from tests.factories import UserFactory
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def user_with_password():
    return UserFactory(password="testpassword!")


def test_login_view_successful_login(client, user_with_password):
    response = client.post(
        reverse("orga:login"),
        {"login_email": user_with_password.email, "login_password": "testpassword!"},
        follow=True,
    )

    assert response.redirect_chain[-1][0] == "/orga/event/"
    assert response.status_code == 200


@pytest.mark.parametrize("event_specific", (True, False))
def test_login_page_offers_password_reset_but_no_registration(
    client, event, event_specific
):
    if event_specific:
        url = f"/orga/event/{event.slug}/login/"
        reset_url = reverse("orga:event.auth.reset", kwargs={"event": event.slug})
    else:
        url = reverse("orga:login")
        reset_url = reverse("orga:auth.reset")

    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert f'href="{reset_url}"' in content
    assert "register_email" not in content


def test_login_view_redirects_authenticated_user(client, user_with_password):
    client.force_login(user_with_password)

    response = client.get(reverse("orga:login"))

    assert response.status_code == 302


def test_login_view_preserves_next_param(client, event):
    user = make_orga_user(event)

    next_url = event.orga_urls.base
    login_url = reverse("orga:login") + f"?next={next_url}"

    response = client.post(
        login_url,
        {"login_email": user.email, "login_password": "testpassword!"},
        follow=True,
    )

    assert response.status_code == 200
    assert response.redirect_chain[-1][0] == next_url


def test_login_view_event_specific_redirects_to_event(client, event):
    user = make_orga_user(event)

    response = client.post(
        f"/orga/event/{event.slug}/login/",
        {"login_email": user.email, "login_password": "testpassword!"},
    )

    assert response.status_code == 302
    assert response.url == f"/orga/event/{event.slug}/"


def test_logout_view_post_logs_out(client, user_with_password):
    client.force_login(user_with_password)

    response = client.post(reverse("orga:logout"))

    assert response.status_code == 302
    # Verify user is logged out by checking login page doesn't redirect
    login_response = client.get(reverse("orga:login"))
    assert login_response.status_code == 200


def test_logout_view_get_does_not_log_out(client, user_with_password):
    client.force_login(user_with_password)

    response = client.get(reverse("orga:logout"))

    assert response.status_code == 302
    # User is still logged in — login page still redirects
    login_response = client.get(reverse("orga:login"))
    assert login_response.status_code == 302


def test_reset_view_sends_email(client, user_with_password):
    djmail.outbox = []

    response = client.post(
        reverse("orga:auth.reset"), {"login_email": user_with_password.email}
    )

    assert response.status_code == 302
    assert response.url == reverse("orga:login")
    user_with_password.refresh_from_db()
    assert user_with_password.pw_reset_token is not None
    assert len(djmail.outbox) == 1


def test_reset_view_blocks_repeated_reset_within_24h(client):
    user = UserFactory(
        pw_reset_token="existingtoken", pw_reset_time=now() - dt.timedelta(hours=1)
    )
    djmail.outbox = []

    response = client.post(reverse("orga:auth.reset"), {"login_email": user.email})

    assert response.status_code == 302
    assert len(djmail.outbox) == 0
    user.refresh_from_db()
    assert user.pw_reset_token == "existingtoken"


def test_reset_view_nonexistent_email_shows_success(client):
    djmail.outbox = []

    response = client.post(
        reverse("orga:auth.reset"), {"login_email": "nobody@example.com"}
    )

    assert response.status_code == 302
    assert len(djmail.outbox) == 0


def test_recover_view_sets_new_password(client):
    user = UserFactory(pw_reset_token="validtoken123", pw_reset_time=now())

    response = client.post(
        f"/orga/reset/{user.pw_reset_token}",
        {"password": "mynewpassword1!", "password_repeat": "mynewpassword1!"},
    )

    assert response.status_code == 302
    assert response.url == reverse("orga:login")
    user.refresh_from_db()
    assert user.pw_reset_token is None
    assert user.check_password("mynewpassword1!")


def test_recover_view_invalid_token_redirects_to_reset(client):
    response = client.post(
        "/orga/reset/bogustoken",
        {"password": "mynewpassword1!", "password_repeat": "mynewpassword1!"},
    )

    assert response.status_code == 302
    assert response.url == reverse("orga:auth.reset")


def test_recover_view_expired_token_redirects_to_reset(client):
    user = UserFactory(
        pw_reset_token="expiredtoken", pw_reset_time=now() - dt.timedelta(days=2)
    )

    response = client.get(f"/orga/reset/{user.pw_reset_token}")

    assert response.status_code == 302
    assert response.url == reverse("orga:auth.reset")


@pytest.mark.parametrize(
    ("password", "password_repeat"),
    (("mynewpassword1!", "differentpassword1!"), ("password", "password")),
    ids=["mismatched", "insecure"],
)
def test_recover_view_invalid_password_keeps_token(client, password, password_repeat):
    user = UserFactory(pw_reset_token="validtoken123", pw_reset_time=now())

    response = client.post(
        f"/orga/reset/{user.pw_reset_token}",
        {"password": password, "password_repeat": password_repeat},
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.pw_reset_token == "validtoken123"


def test_login_view_gates_unverified_user_without_sending_mail(client):
    user = UserFactory(
        password="testpassword!",
        email_verification_state=EmailVerificationState.UNVERIFIED,
    )
    djmail.outbox = []

    response = client.post(
        reverse("orga:login"),
        {"login_email": user.email, "login_password": "testpassword!"},
        follow=True,
    )

    assert response.redirect_chain[-1][0] == "/orga/verify/"
    assert djmail.outbox == []


def test_reset_view_event_specific_redirects_to_event_login(client, event):
    url = reverse("orga:event.auth.reset", kwargs={"event": event.slug})

    response = client.post(url, {"login_email": "nobody@example.com"})

    assert response.status_code == 302
    expected = reverse("orga:event.login", kwargs={"event": event.slug})
    assert response.url == expected


def _age_session(client, seconds):
    session = client.session
    session["pretalx_auth_login_time"] = int(time.time()) - seconds
    session["pretalx_auth_last_used"] = int(time.time()) - seconds
    session.save()


@override_settings(PRETALX_SESSION_TIMEOUT_RELATIVE=100)
def test_reauth_with_correct_password_restores_access(client, user_with_password):
    client.force_login(user_with_password)
    _age_session(client, 200)

    response = client.post(
        "/orga/reauth/?next=/orga/event/", {"password": "testpassword!"}
    )

    assert response.status_code == 302
    assert response.url == "/orga/event/"
    assert client.get(reverse("orga:event.list")).status_code == 200


@override_settings(PRETALX_SESSION_TIMEOUT_RELATIVE=100)
def test_reauth_with_wrong_password_keeps_challenging(client, user_with_password):
    client.force_login(user_with_password)
    _age_session(client, 200)

    response = client.post("/orga/reauth/", {"password": "nope"})

    assert response.status_code == 200
    assert (
        client.get(reverse("orga:event.list")).url == "/orga/reauth/?next=/orga/event/"
    )


@override_settings(PRETALX_SESSION_TIMEOUT_ABSOLUTE=100)
def test_expired_orga_session_is_logged_out(client, user_with_password):
    client.force_login(user_with_password)
    _age_session(client, 200)

    response = client.get(reverse("orga:event.list"))

    assert response.status_code == 302
    assert response.url == "/orga/login/?next=/orga/event/"
    assert SESSION_KEY not in client.session


@override_settings(PRETALX_SESSION_TIMEOUT_RELATIVE=100)
@pytest.mark.parametrize("slug", ("democon", "orgacon"))
def test_idle_session_does_not_affect_public_pages(
    client, user_with_password, event, slug
):
    event.slug = slug
    event.is_public = True
    event.save()
    client.force_login(user_with_password)
    _age_session(client, 200)

    assert client.get(f"/{slug}/").status_code == 200


@override_settings(PRETALX_SESSION_TIMEOUT_RELATIVE=100)
def test_idle_orga_session_answers_background_requests_with_a_login_url(
    client, user_with_password
):
    client.force_login(user_with_password)
    _age_session(client, 200)

    response = client.get(
        reverse("orga:event.list"), headers={"X-Requested-With": "XMLHttpRequest"}
    )

    assert response.status_code == 401
    assert response["X-Login-Url"] == "/orga/reauth/"


@override_settings(PRETALX_SESSION_TIMEOUT_ABSOLUTE=100)
def test_expired_orga_session_answers_background_requests_with_a_login_url(
    client, user_with_password
):
    client.force_login(user_with_password)
    _age_session(client, 200)

    response = client.get(
        reverse("orga:event.list"), headers={"X-Requested-With": "XMLHttpRequest"}
    )

    assert response.status_code == 401
    assert response["X-Login-Url"] == "/orga/login/"
    assert response.json() == {"detail": "Authentication required"}
    assert SESSION_KEY not in client.session


@override_settings(PRETALX_SESSION_TIMEOUT_ABSOLUTE=100)
def test_expired_orga_session_points_background_requests_at_the_event_login(
    client, organiser_user, event
):
    client.force_login(organiser_user)
    _age_session(client, 200)

    response = client.get(
        event.orga_urls.base, headers={"X-Requested-With": "XMLHttpRequest"}
    )

    assert response.status_code == 401
    assert response["X-Login-Url"] == f"/orga/event/{event.slug}/login/"


@pytest.mark.parametrize(("keep_logged_in", "expected"), ((True, True), (False, False)))
def test_orga_login_sets_long_session_only_when_asked(
    client, user_with_password, keep_logged_in, expected
):
    data = {"login_email": user_with_password.email, "login_password": "testpassword!"}
    if keep_logged_in:
        data["keep_logged_in"] = "on"

    client.post(reverse("orga:login"), data)

    assert client.session["pretalx_auth_long_session"] is expected
