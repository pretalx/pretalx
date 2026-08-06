# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from datetime import timedelta

import pytest
from django.utils.timezone import now
from rest_framework.exceptions import AuthenticationFailed

from pretalx.api.auth import UserTokenAuthentication
from tests.factories import EventFactory, UserApiTokenFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_user_token_authentication_valid_token():
    token = UserApiTokenFactory()
    auth = UserTokenAuthentication()

    user, returned_token = auth.authenticate_credentials(token.token)

    assert user == token.user
    assert returned_token == token


def test_user_token_authentication_prefetches_events(django_assert_num_queries):
    token = UserApiTokenFactory()
    event = EventFactory()
    token.limit_events.add(event)
    auth = UserTokenAuthentication()

    _, returned_token = auth.authenticate_credentials(token.token)

    with django_assert_num_queries(0):
        events = list(returned_token.limit_events.all())
    assert events == [event]


def test_user_token_authentication_sets_last_used():
    token = UserApiTokenFactory()
    auth = UserTokenAuthentication()

    _, returned_token = auth.authenticate_credentials(token.token)

    token.refresh_from_db()
    assert token.last_used is not None
    assert token.last_used == returned_token.last_used
    assert now() - token.last_used < timedelta(seconds=30)


@pytest.mark.parametrize(("age", "expected_update"), ((10, False), (600, True)))
def test_user_token_authentication_debounces_last_used(age, expected_update):
    previous = now() - timedelta(seconds=age)
    token = UserApiTokenFactory(last_used=previous)
    auth = UserTokenAuthentication()

    auth.authenticate_credentials(token.token)

    token.refresh_from_db()
    assert (token.last_used != previous) is expected_update


def test_user_token_authentication_invalid_token():
    auth = UserTokenAuthentication()

    with pytest.raises(AuthenticationFailed, match="Invalid token"):
        auth.authenticate_credentials("nonexistent-token-value")


def test_user_token_authentication_expired_token():
    token = UserApiTokenFactory(expires=now() - timedelta(days=1))
    auth = UserTokenAuthentication()

    with pytest.raises(AuthenticationFailed, match="Invalid token"):
        auth.authenticate_credentials(token.token)
