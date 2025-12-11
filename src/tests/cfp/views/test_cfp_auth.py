# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from unittest.mock import patch

import pytest
from django.test import override_settings

from pretalx.common.auth import get_client_ip
from pretalx.person.forms.user import UserForm


@pytest.mark.django_db
def test_can_login_with_email(speaker, client, event):
    response = client.post(
        event.urls.login,
        data={"login_email": "jane@speaker.org", "login_password": "speakerpwd1!"},
        follow=True,
    )
    assert response.status_code == 200
    assert speaker.get_display_name() in response.text


@pytest.mark.django_db
def test_cannot_login_with_incorrect_email(client, event, speaker):
    response = client.post(
        event.urls.login,
        data={"login_email": "jane001@me.space", "login_password": "speakerpwd1!"},
        follow=True,
    )
    assert response.status_code == 200
    assert speaker.get_display_name() not in response.text


@pytest.mark.django_db
def test_cfp_logout(speaker_client, event, speaker):
    response = speaker_client.get(
        event.urls.logout,
        follow=True,
    )
    assert response.status_code == 200
    assert speaker.get_display_name() in response.text
    response = speaker_client.post(
        event.urls.logout,
        follow=True,
    )
    assert response.status_code == 200
    assert speaker.get_display_name() not in response.text


@pytest.mark.django_db
def test_can_reset_password_by_email(speaker, client, event):
    response = client.post(
        event.urls.reset,
        data={
            "login_email": speaker.email,
        },
        follow=True,
    )
    assert response.status_code == 200
    speaker.refresh_from_db()
    assert speaker.pw_reset_token
    response = client.post(
        event.urls.reset + f"/{speaker.pw_reset_token}",
        data={"password": "mynewpassword1!", "password_repeat": "mynewpassword1!"},
        follow=True,
    )
    assert response.status_code == 200
    speaker.refresh_from_db()
    assert not speaker.pw_reset_token
    response = client.post(
        event.urls.login,
        data={"login_email": speaker.email, "login_password": "mynewpassword1!"},
        follow=True,
    )
    assert speaker.get_display_name() in response.text


@pytest.mark.django_db
def test_cannot_use_incorrect_token(speaker, client, event):
    response = client.post(
        event.urls.reset + "/abcdefg",
        data={"password": "mynewpassword1!", "password_repeat": "mynewpassword1!"},
        follow=True,
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_cannot_reset_password_with_incorrect_input(speaker, client, event):
    response = client.post(
        event.urls.reset,
        data={
            "login_email": speaker.email,
        },
        follow=True,
    )
    assert response.status_code == 200
    speaker.refresh_from_db()
    assert speaker.pw_reset_token
    response = client.post(
        event.urls.reset + f"/{speaker.pw_reset_token}",
        data={"password": "mynewpassword1!", "password_repeat": "mynewpassword123!"},
        follow=True,
    )
    assert response.status_code == 200
    speaker.refresh_from_db()
    assert speaker.pw_reset_token
    response = client.post(
        event.urls.login,
        data={"login_email": speaker.email, "login_password": "mynewpassword1!"},
        follow=True,
    )
    assert speaker.get_display_name() not in response.text


@pytest.mark.django_db
def test_cannot_reset_password_to_insecure_password(speaker, client, event):
    response = client.post(
        event.urls.reset,
        data={
            "login_email": speaker.email,
        },
        follow=True,
    )
    assert response.status_code == 200
    speaker.refresh_from_db()
    assert speaker.pw_reset_token
    response = client.post(
        event.urls.reset + f"/{speaker.pw_reset_token}",
        data={"password": "password", "password_repeat": "password"},
        follow=True,
    )
    assert response.status_code == 200
    speaker.refresh_from_db()
    assert speaker.pw_reset_token
    response = client.post(
        event.urls.login,
        data={"login_email": speaker.email, "login_password": "mynewpassword1!"},
        follow=True,
    )
    assert speaker.get_display_name() not in response.text


@pytest.mark.django_db
def test_cannot_reset_password_without_account(speaker, client, event):
    response = client.post(
        event.urls.reset,
        data={
            "login_email": "incorrect" + speaker.email,
        },
        follow=True,
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    "remote_addr,x_forwarded_for,expected",
    [
        ("192.168.1.1", None, "192.168.1.1"),
        ("127.0.0.1", "203.0.113.1, 10.0.0.1", "203.0.113.1"),
        ("127.0.0.1", "  8.8.8.8  ", "8.8.8.8"),
    ],
)
def test_get_client_ip(rf, remote_addr, x_forwarded_for, expected):
    request = rf.get("/")
    request.META["REMOTE_ADDR"] = remote_addr
    if x_forwarded_for:
        request.META["HTTP_X_FORWARDED_FOR"] = x_forwarded_for
    assert get_client_ip(request) == expected


@pytest.mark.django_db
@override_settings(HAS_REDIS=True)
def test_login_rate_limiting_blocks_after_threshold(speaker, rf):
    request = rf.post("/login/")
    request.META["REMOTE_ADDR"] = "8.8.8.8"

    with patch("pretalx.person.forms.user.cache") as mock_cache:
        mock_cache.get.return_value = 11

        form = UserForm(
            data={"login_email": "jane@speaker.org", "login_password": "wrongpwd"},
            request=request,
        )
        assert form.ratelimit_key is not None
        assert not form.is_valid()
        assert "5 minutes" in str(form.errors)


@pytest.mark.django_db
@override_settings(HAS_REDIS=True)
def test_login_increments_counter_on_failure(speaker, rf):
    request = rf.post("/login/")
    request.META["REMOTE_ADDR"] = "8.8.8.8"

    with patch("pretalx.person.forms.user.cache") as mock_cache:
        mock_cache.get.return_value = 5

        form = UserForm(
            data={"login_email": "jane@speaker.org", "login_password": "wrongpwd"},
            request=request,
        )
        form.is_valid()

        mock_cache.incr.assert_called_once()


@pytest.mark.django_db
@override_settings(HAS_REDIS=True)
def test_login_sets_counter_on_first_failure(speaker, rf):
    request = rf.post("/login/")
    request.META["REMOTE_ADDR"] = "8.8.8.8"

    with patch("pretalx.person.forms.user.cache") as mock_cache:
        mock_cache.get.return_value = 0
        mock_cache.incr.side_effect = ValueError("Key not found")

        form = UserForm(
            data={"login_email": "jane@speaker.org", "login_password": "wrongpwd"},
            request=request,
        )
        form.is_valid()

        mock_cache.incr.assert_called_once()
        mock_cache.set.assert_called_once()
        call_args = mock_cache.set.call_args
        assert call_args[0][1] == 1
        assert call_args[0][2] == 300


@pytest.mark.django_db
@override_settings(HAS_REDIS=True)
def test_login_does_not_increment_counter_on_success(speaker, rf):
    request = rf.post("/login/")
    request.META["REMOTE_ADDR"] = "8.8.8.8"

    with patch("pretalx.person.forms.user.cache") as mock_cache:
        mock_cache.get.return_value = 5

        form = UserForm(
            data={"login_email": "jane@speaker.org", "login_password": "speakerpwd1!"},
            request=request,
        )
        assert form.is_valid()
        mock_cache.incr.assert_not_called()
        mock_cache.set.assert_not_called()


@pytest.mark.django_db
@override_settings(HAS_REDIS=True)
def test_login_no_rate_limiting_for_private_ip(speaker, rf):
    request = rf.post("/login/")
    request.META["REMOTE_ADDR"] = "192.168.1.1"

    with patch("pretalx.person.forms.user.cache") as mock_cache:
        mock_cache.get.return_value = 100

        form = UserForm(
            data={"login_email": "jane@speaker.org", "login_password": "wrongpwd"},
            request=request,
        )
        form.is_valid()
        assert "5 minutes" not in str(form.errors)


@pytest.mark.django_db
@override_settings(HAS_REDIS=False)
def test_login_no_rate_limiting_without_redis(speaker, rf):
    request = rf.post("/login/")
    request.META["REMOTE_ADDR"] = "8.8.8.8"

    form = UserForm(
        data={"login_email": "jane@speaker.org", "login_password": "wrongpwd"},
        request=request,
    )
    form.is_valid()
    assert "5 minutes" not in str(form.errors)
