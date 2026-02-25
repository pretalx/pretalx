from datetime import timedelta

import pytest
from django.test import RequestFactory
from django.utils.timezone import now
from rest_framework.exceptions import AuthenticationFailed

from pretalx.common.auth import UserTokenAuthentication, get_client_ip
from tests.factories import EventFactory, UserApiTokenFactory

pytestmark = pytest.mark.unit

rf = RequestFactory()


@pytest.mark.parametrize(
    ("forwarded_for", "expected"),
    (
        ("10.0.0.1, 10.0.0.2", "10.0.0.1"),
        ("10.0.0.1", "10.0.0.1"),
        ("  10.0.0.1  , 10.0.0.2", "10.0.0.1"),
    ),
)
def test_get_client_ip_from_x_forwarded_for(forwarded_for, expected):
    request = rf.get("/")
    request.META["HTTP_X_FORWARDED_FOR"] = forwarded_for

    assert get_client_ip(request) == expected


def test_get_client_ip_no_forwarded_for_falls_back_to_remote_addr():
    request = rf.get("/")
    request.META.pop("HTTP_X_FORWARDED_FOR", None)
    request.META["REMOTE_ADDR"] = "127.0.0.1"

    assert get_client_ip(request) == "127.0.0.1"


@pytest.mark.django_db
def test_user_token_authentication_valid_token():
    token = UserApiTokenFactory()
    auth = UserTokenAuthentication()

    user, returned_token = auth.authenticate_credentials(token.token)

    assert user == token.user
    assert returned_token == token


@pytest.mark.django_db
def test_user_token_authentication_prefetches_events(django_assert_num_queries):
    token = UserApiTokenFactory()
    event = EventFactory()
    token.events.add(event)
    auth = UserTokenAuthentication()

    _, returned_token = auth.authenticate_credentials(token.token)

    with django_assert_num_queries(0):
        events = list(returned_token.events.all())
    assert events == [event]


@pytest.mark.django_db
def test_user_token_authentication_invalid_token():
    auth = UserTokenAuthentication()

    with pytest.raises(AuthenticationFailed, match="Invalid token"):
        auth.authenticate_credentials("nonexistent-token-value")


@pytest.mark.django_db
def test_user_token_authentication_expired_token():
    token = UserApiTokenFactory(expires=now() - timedelta(days=1))
    auth = UserTokenAuthentication()

    with pytest.raises(AuthenticationFailed, match="Invalid token"):
        auth.authenticate_credentials(token.token)
