# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import time
from importlib import import_module

import pytest
from django.conf import settings
from django.test import override_settings

from pretalx.common.security import (
    SessionInvalidError,
    SessionReauthRequiredError,
    assert_session_valid,
    session_login,
    session_reauth,
)
from tests.factories import UserFactory
from tests.utils import make_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _request(user, **session):
    request = make_request(None, user=user, path="/orga/event/")
    request.session.update(session)
    return request


def _login_request():
    request = make_request(None, path="/orga/login/")
    request.session = import_module(settings.SESSION_ENGINE).SessionStore()
    return request


def test_assert_session_valid_refreshes_last_used():
    request = _request(
        UserFactory(),
        pretalx_auth_login_time=int(time.time()) - 10,
        pretalx_auth_last_used=int(time.time()) - 10,
    )

    assert assert_session_valid(request) is True
    assert request.session["pretalx_auth_last_used"] == pytest.approx(
        int(time.time()), abs=2
    )


@override_settings(PRETALX_SESSION_TIMEOUT_ABSOLUTE=100)
def test_assert_session_valid_starts_the_absolute_clock_for_sessions_without_one():
    request = _request(UserFactory(), pretalx_auth_last_used=int(time.time()))

    assert assert_session_valid(request) is True
    assert request.session["pretalx_auth_login_time"] == pytest.approx(
        int(time.time()), abs=2
    )
    assert "pretalx_auth_long_session" not in request.session


@override_settings(PRETALX_SESSION_TIMEOUT_RELATIVE=100)
def test_assert_session_valid_still_challenges_an_idle_session_without_a_login_time():
    request = _request(UserFactory(), pretalx_auth_last_used=int(time.time()) - 200)

    with pytest.raises(SessionReauthRequiredError):
        assert_session_valid(request)


@override_settings(PRETALX_SESSION_TIMEOUT_ABSOLUTE=100)
def test_assert_session_valid_raises_on_absolute_timeout():
    request = _request(
        UserFactory(),
        pretalx_auth_login_time=int(time.time()) - 200,
        pretalx_auth_last_used=int(time.time()),
    )

    with pytest.raises(SessionInvalidError):
        assert_session_valid(request)

    assert request.session["pretalx_auth_login_time"] == 0


@override_settings(PRETALX_SESSION_TIMEOUT_RELATIVE=100)
def test_assert_session_valid_raises_on_idle_timeout():
    request = _request(
        UserFactory(),
        pretalx_auth_login_time=int(time.time()) - 200,
        pretalx_auth_last_used=int(time.time()) - 200,
    )

    with pytest.raises(SessionReauthRequiredError):
        assert_session_valid(request)

    # The idle timeout must not end the session, so the login time survives.
    assert request.session["pretalx_auth_login_time"] != 0


@override_settings(
    PRETALX_SESSION_TIMEOUT_RELATIVE=100, PRETALX_SESSION_TIMEOUT_ABSOLUTE=100
)
def test_assert_session_valid_ignores_timeouts_for_long_sessions():
    request = _request(
        UserFactory(),
        pretalx_auth_login_time=int(time.time()) - 200,
        pretalx_auth_last_used=int(time.time()) - 200,
        pretalx_auth_long_session=True,
    )

    assert assert_session_valid(request) is True


@pytest.mark.parametrize("keep_logged_in", (True, False))
def test_session_login_sets_long_session_flag(keep_logged_in):
    user = UserFactory()
    request = _login_request()

    session_login(request, user, keep_logged_in=keep_logged_in)

    assert request.session["pretalx_auth_long_session"] is keep_logged_in
    assert request.user == user


def test_session_login_records_both_timestamps():
    request = _login_request()

    session_login(request, UserFactory())

    assert request.session["pretalx_auth_login_time"] == pytest.approx(
        int(time.time()), abs=2
    )
    assert (
        request.session["pretalx_auth_last_used"]
        == request.session["pretalx_auth_login_time"]
    )


def test_session_reauth_resets_both_timers():
    request = _request(
        UserFactory(), pretalx_auth_login_time=1, pretalx_auth_last_used=2
    )

    session_reauth(request)

    assert request.session["pretalx_auth_login_time"] == pytest.approx(
        int(time.time()), abs=2
    )
    assert (
        request.session["pretalx_auth_last_used"]
        == request.session["pretalx_auth_login_time"]
    )
