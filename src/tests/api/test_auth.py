# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from datetime import timedelta

import pytest
from django.utils.timezone import now
from rest_framework.exceptions import AuthenticationFailed

from pretalx.api.auth import UserTokenAuthentication
from pretalx.api.versions import CURRENT_VERSION, UNSUPPORTED_VERSION_MESSAGE
from tests.factories import EventFactory, TeamFactory, UserApiTokenFactory
from tests.utils import make_api_request, make_orga_user

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


@pytest.mark.parametrize(
    ("stored_version", "version_header", "expected_message"),
    (
        ("LEGACY", None, UNSUPPORTED_VERSION_MESSAGE.format(version="LEGACY")),
        ("v-nonexistent", None, "Unsupported version: v-nonexistent"),
        ("v1", "LEGACY", UNSUPPORTED_VERSION_MESSAGE.format(version="LEGACY")),
        (None, "v-nonexistent", "Unsupported version: v-nonexistent"),
        ("LEGACY", "v-nonexistent", "Unsupported version: v-nonexistent"),
    ),
    ids=[
        "removed",
        "unknown",
        "removed_header",
        "unknown_header",
        "removed_with_unknown_header",
    ],
)
def test_user_token_authentication_rejects_unsupported_version(
    stored_version, version_header, expected_message
):
    token = UserApiTokenFactory(
        user=make_orga_user(EventFactory()), version=stored_version
    )
    request = make_api_request()
    request.META["HTTP_AUTHORIZATION"] = f"Token {token.token}"
    if version_header:
        request.META["HTTP_PRETALX_VERSION"] = version_header
    auth = UserTokenAuthentication()

    with pytest.raises(AuthenticationFailed) as excinfo:
        auth.authenticate(request)

    assert str(excinfo.value.detail) == expected_message


@pytest.mark.parametrize(
    ("stored_version", "version_header"),
    (("LEGACY", CURRENT_VERSION), ("v1", None), (None, None)),
    ids=["removed_with_supported_header", "supported", "unset"],
)
def test_user_token_authentication_accepts_supported_version(
    stored_version, version_header
):
    token = UserApiTokenFactory(
        user=make_orga_user(EventFactory()), version=stored_version
    )
    request = make_api_request()
    request.META["HTTP_AUTHORIZATION"] = f"Token {token.token}"
    if version_header:
        request.META["HTTP_PRETALX_VERSION"] = version_header
    auth = UserTokenAuthentication()

    assert auth.authenticate(request) == (token.user, token)
