# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.conf import settings
from django.test import override_settings

from pretalx.api.throttling import AuthenticatedRateThrottle
from tests.factories import UserApiTokenFactory, UserFactory
from tests.utils import make_api_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def rest_framework(**rates):
    return {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": rates}


def token_request(token):
    return make_api_request(auth=token, user=token.user)


@override_settings(REST_FRAMEWORK=rest_framework(user="3/minute"))
def test_throttle_allows_requests_up_to_the_limit():
    token = UserApiTokenFactory(user=UserFactory())
    throttle = AuthenticatedRateThrottle()

    results = [throttle.allow_request(token_request(token), None) for _ in range(4)]

    assert results == [True, True, True, False]
    assert 0 < throttle.wait() <= 60


@override_settings(REST_FRAMEWORK=rest_framework(user="2/minute"))
def test_throttle_shares_one_budget_across_a_users_tokens_and_session():
    user = UserFactory()
    first_token = UserApiTokenFactory(user=user)
    second_token = UserApiTokenFactory(user=user)
    throttle = AuthenticatedRateThrottle()

    first = throttle.allow_request(token_request(first_token), None)
    second = throttle.allow_request(token_request(second_token), None)
    third = throttle.allow_request(make_api_request(user=user), None)

    assert [first, second, third] == [True, True, False]


@override_settings(REST_FRAMEWORK=rest_framework(user="1/minute"))
def test_throttle_gives_each_user_its_own_budget():
    user = UserFactory()
    throttle = AuthenticatedRateThrottle()

    first = throttle.allow_request(make_api_request(user=user), None)
    second = throttle.allow_request(make_api_request(user=UserFactory()), None)
    third = throttle.allow_request(make_api_request(user=user), None)

    assert [first, second, third] == [True, True, False]


@override_settings(REST_FRAMEWORK=rest_framework(user="1/minute"))
def test_throttle_skips_anonymous_requests():
    throttle = AuthenticatedRateThrottle()
    request = make_api_request()

    assert throttle.get_cache_key(request, None) is None
    assert [throttle.allow_request(request, None) for _ in range(3)] == [True] * 3


@override_settings(REST_FRAMEWORK=rest_framework(user=None))
def test_throttle_is_disabled_without_a_rate():
    token = UserApiTokenFactory(user=UserFactory())
    throttle = AuthenticatedRateThrottle()

    assert throttle.rate is None
    assert [throttle.allow_request(token_request(token), None) for _ in range(5)] == [
        True
    ] * 5
