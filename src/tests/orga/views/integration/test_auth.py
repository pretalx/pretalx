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

from pretalx.orga.views.auth import RecoverView
from pretalx.person.enums import EmailVerificationState
from pretalx.person.models import User
from tests.factories import UserFactory
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def user_with_password():
    return UserFactory(password="testpassword!")


def test_login_logout_round_trip(client, user_with_password):
    login_url = reverse("orga:login")
    data = {"login_email": user_with_password.email, "login_password": "testpassword!"}

    response = client.get(login_url)

    assert response.status_code == 200
    content = response.content.decode()
    assert f'href="{reverse("orga:auth.reset")}"' in content
    assert "register_email" not in content

    response = client.post(login_url, data, follow=True)

    assert response.redirect_chain[-1][0] == "/orga/event/"
    assert response.status_code == 200
    assert client.session["pretalx_auth_long_session"] is False
    assert client.get(login_url).status_code == 302

    response = client.get(reverse("orga:logout"))

    assert response.status_code == 302
    assert client.get(login_url).status_code == 302

    response = client.post(reverse("orga:logout"))

    assert response.status_code == 302
    assert client.get(login_url).status_code == 200

    client.post(login_url, {**data, "keep_logged_in": "on"})

    assert client.session["pretalx_auth_long_session"] is True


def test_event_specific_login_and_reset(client, event):
    user = make_orga_user(event)
    login_url = f"/orga/event/{event.slug}/login/"
    data = {"login_email": user.email, "login_password": "testpassword!"}

    response = client.get(login_url)

    assert response.status_code == 200
    content = response.content.decode()
    reset_url = reverse("orga:event.auth.reset", kwargs={"event": event.slug})
    assert f'href="{reset_url}"' in content
    assert "register_email" not in content

    response = client.post(reset_url, {"login_email": "nobody@example.com"})

    assert response.status_code == 302
    assert response.url == login_url

    response = client.post(login_url, data)

    assert response.status_code == 302
    assert response.url == f"/orga/event/{event.slug}/"

    client.post(reverse("orga:logout"))
    next_url = event.orga_urls.base
    response = client.post(
        f"{reverse('orga:login')}?next={next_url}", data, follow=True
    )

    assert response.status_code == 200
    assert response.redirect_chain[-1][0] == next_url


def test_reset_and_recover_password(client, user_with_password):
    djmail.outbox = []
    reset_url = reverse("orga:auth.reset")

    response = client.post(reset_url, {"login_email": user_with_password.email})

    assert response.status_code == 302
    assert response.url == reverse("orga:login")
    user_with_password.refresh_from_db()
    token = user_with_password.pw_reset_token
    assert token is not None
    assert len(djmail.outbox) == 1

    response = client.post(reset_url, {"login_email": user_with_password.email})

    assert response.status_code == 302
    assert len(djmail.outbox) == 1
    user_with_password.refresh_from_db()
    assert user_with_password.pw_reset_token == token

    response = client.post(reset_url, {"login_email": "nobody@example.com"})

    assert response.status_code == 302
    assert len(djmail.outbox) == 1

    response = client.post(
        f"/orga/reset/{token}",
        {"password": "mynewpassword1!", "password_repeat": "mynewpassword1!"},
    )

    assert response.status_code == 302
    assert response.url == reverse("orga:login")
    user_with_password.refresh_from_db()
    assert user_with_password.pw_reset_token is None
    assert user_with_password.check_password("mynewpassword1!")

    response = client.post(
        f"/orga/reset/{token}",
        {"password": "othernewpassword1!", "password_repeat": "othernewpassword1!"},
    )

    assert response.status_code == 302
    assert response.url == reverse("orga:auth.reset")
    user_with_password.refresh_from_db()
    assert user_with_password.check_password("mynewpassword1!")


def test_recover_view_invalid_password_or_expired_token_keeps_password(client):
    user = UserFactory(
        password="testpassword!", pw_reset_token="validtoken123", pw_reset_time=now()
    )
    url = f"/orga/reset/{user.pw_reset_token}"

    for password, password_repeat in (
        ("mynewpassword1!", "differentpassword1!"),
        ("password", "password"),
        ("", ""),
    ):
        response = client.post(
            url, {"password": password, "password_repeat": password_repeat}
        )
        assert response.status_code == 200, password
        user.refresh_from_db()
        assert user.pw_reset_token == "validtoken123", password
        assert user.check_password("testpassword!"), password

    User.objects.filter(pk=user.pk).update(pw_reset_time=now() - dt.timedelta(days=2))

    response = client.get(url)

    assert response.status_code == 302
    assert response.url == reverse("orga:auth.reset")


def test_recover_view_token_consumed_by_concurrent_request(client, monkeypatch):
    user = UserFactory(
        password="testpassword!", pw_reset_token="validtoken123", pw_reset_time=now()
    )
    original = RecoverView.get_user

    def racing_get_user(self):
        found = original(self)
        User.objects.filter(pk=found.pk).update(pw_reset_token=None, pw_reset_time=None)
        return found

    monkeypatch.setattr(RecoverView, "get_user", racing_get_user)

    response = client.post(
        "/orga/reset/validtoken123",
        {"password": "mynewpassword1!", "password_repeat": "mynewpassword1!"},
    )

    assert response.status_code == 302
    assert response.url == reverse("orga:auth.reset")
    user.refresh_from_db()
    assert user.check_password("testpassword!")
    assert not user.check_password("mynewpassword1!")


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


def _age_session(client, seconds):
    session = client.session
    session["pretalx_auth_login_time"] = int(time.time()) - seconds
    session["pretalx_auth_last_used"] = int(time.time()) - seconds
    session.save()


@override_settings(PRETALX_SESSION_TIMEOUT_RELATIVE=100)
def test_idle_orga_session_challenges_until_reauth(client, user_with_password):
    client.force_login(user_with_password)
    _age_session(client, 200)

    response = client.get(
        reverse("orga:event.list"), headers={"X-Requested-With": "XMLHttpRequest"}
    )

    assert response.status_code == 401
    assert response["X-Login-Url"] == "/orga/reauth/"

    response = client.get(reverse("orga:event.list"))

    assert response.status_code == 302
    assert response.url == "/orga/reauth/?next=/orga/event/"

    response = client.post("/orga/reauth/", {"password": "nope"})

    assert response.status_code == 200
    assert (
        client.get(reverse("orga:event.list")).url == "/orga/reauth/?next=/orga/event/"
    )

    response = client.post(
        "/orga/reauth/?next=/orga/event/", {"password": "testpassword!"}
    )

    assert response.status_code == 302
    assert response.url == "/orga/event/"
    assert client.get(reverse("orga:event.list")).status_code == 200


@override_settings(PRETALX_SESSION_TIMEOUT_ABSOLUTE=100)
def test_expired_orga_session_is_logged_out(client, organiser_user, event):
    client.force_login(organiser_user)
    _age_session(client, 200)

    response = client.get(reverse("orga:event.list"))

    assert response.status_code == 302
    assert response.url == "/orga/login/?next=/orga/event/"
    assert SESSION_KEY not in client.session

    client.force_login(organiser_user)
    _age_session(client, 200)
    response = client.get(
        reverse("orga:event.list"), headers={"X-Requested-With": "XMLHttpRequest"}
    )

    assert response.status_code == 401
    assert response["X-Login-Url"] == "/orga/login/"
    assert response.json() == {"detail": "Authentication required"}
    assert SESSION_KEY not in client.session

    client.force_login(organiser_user)
    _age_session(client, 200)
    response = client.get(
        event.orga_urls.base, headers={"X-Requested-With": "XMLHttpRequest"}
    )

    assert response.status_code == 401
    assert response["X-Login-Url"] == f"/orga/event/{event.slug}/login/"


@override_settings(PRETALX_SESSION_TIMEOUT_RELATIVE=100)
def test_idle_session_does_not_affect_public_pages(client, user_with_password, event):
    client.force_login(user_with_password)
    _age_session(client, 200)

    for slug in ("democon", "orgacon"):
        event.slug = slug
        event.save()
        assert client.get(f"/{slug}/").status_code == 200, slug
