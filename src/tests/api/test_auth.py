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
    token.events.add(event)
    auth = UserTokenAuthentication()

    _, returned_token = auth.authenticate_credentials(token.token)

    with django_assert_num_queries(0):
        events = list(returned_token.events.all())
    assert events == [event]


def test_user_token_authentication_invalid_token():
    auth = UserTokenAuthentication()

    with pytest.raises(AuthenticationFailed, match="Invalid token"):
        auth.authenticate_credentials("nonexistent-token-value")


def test_user_token_authentication_expired_token():
    token = UserApiTokenFactory(expires=now() - timedelta(days=1))
    auth = UserTokenAuthentication()

    with pytest.raises(AuthenticationFailed, match="Invalid token"):
        auth.authenticate_credentials(token.token)
