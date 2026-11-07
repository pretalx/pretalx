# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from datetime import timedelta

import pytest
from django.utils.timezone import now
from rest_framework.exceptions import AuthenticationFailed

from pretalx.api.auth import UserTokenAuthentication
from tests.factories import EventFactory, TeamFactory, UserApiTokenFactory
from tests.utils import make_orga_user

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_user_token_authentication_valid_token(django_assert_num_queries):
    event = EventFactory()
    token = UserApiTokenFactory(user=make_orga_user(event))
    token.limit_events.add(event)
    auth = UserTokenAuthentication()

    user, returned_token = auth.authenticate_credentials(token.token)

    assert user == token.user
    assert returned_token == token
    with django_assert_num_queries(0):
        assert list(returned_token.limit_events.all()) == [event]
    token.refresh_from_db()
    assert token.last_used is not None
    assert token.last_used == returned_token.last_used
    assert now() - token.last_used < timedelta(seconds=30)


@pytest.mark.parametrize(("age", "expected_update"), ((10, False), (600, True)))
def test_user_token_authentication_debounces_last_used(age, expected_update):
    previous = now() - timedelta(seconds=age)
    token = UserApiTokenFactory(user=make_orga_user(EventFactory()), last_used=previous)
    auth = UserTokenAuthentication()

    auth.authenticate_credentials(token.token)

    token.refresh_from_db()
    assert (token.last_used != previous) is expected_update


def test_user_token_authentication_invalid_token():
    auth = UserTokenAuthentication()

    with pytest.raises(AuthenticationFailed, match="Invalid token"):
        auth.authenticate_credentials("nonexistent-token-value")


@pytest.mark.parametrize(
    ("token_kwargs", "has_team"),
    (
        ({"expires": now() - timedelta(days=1)}, True),
        ({"user__is_active": False}, True),
        ({}, False),
    ),
    ids=["expired", "deactivated_user", "no_team"],
)
def test_user_token_authentication_rejects_token(token_kwargs, has_team):
    token = UserApiTokenFactory(all_events=True, **token_kwargs)
    if has_team:
        TeamFactory(organiser=EventFactory().organiser, all_events=True).members.add(
            token.user
        )
    auth = UserTokenAuthentication()

    with pytest.raises(AuthenticationFailed, match="Invalid token"):
        auth.authenticate_credentials(token.token)

    token.refresh_from_db()
    assert token.last_used is None
