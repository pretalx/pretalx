# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.core.exceptions import ValidationError
from django.utils.timezone import now as tz_now

from pretalx.api.versions import CURRENT_VERSION, DEV_PREVIEW
from pretalx.person.models import UserApiToken
from pretalx.person.models.auth_token import (
    ENDPOINTS,
    READ_PERMISSIONS,
    WRITE_PERMISSIONS,
    generate_api_token,
)
from tests.factories import EventFactory, UserApiTokenFactory, UserFactory

pytestmark = pytest.mark.unit


def test_generate_api_token_format_and_uniqueness():
    token = generate_api_token()
    assert len(token) == 64
    assert token.isalnum()
    assert token == token.lower()
    assert token != generate_api_token()


@pytest.mark.parametrize(
    ("endpoints", "endpoint", "method", "expected"),
    (
        ({"events": ["list", "retrieve"]}, "events", "list", True),
        ({"events": ["list"]}, "events", "retrieve", False),
        ({}, "events", "list", False),
        ({"events": ["update"]}, "events", "partial_update", True),
        ({"events": ["actions"]}, "events", "some_custom_method", True),
        ({"events": ["list"]}, "events", "some_custom_method", False),
    ),
    ids=[
        "in_list",
        "not_in_list",
        "missing_endpoint",
        "partial_update_maps_to_update",
        "unknown_maps_to_actions",
        "unknown_without_actions",
    ],
)
def test_user_api_token_has_endpoint_permission(endpoints, endpoint, method, expected):
    token = UserApiToken(endpoints=endpoints)
    assert token.has_endpoint_permission(endpoint, method) is expected


@pytest.mark.parametrize(
    ("endpoints", "expected"),
    (
        ({}, False),
        ({"events": []}, False),
        ({"events": ["list", "retrieve"]}, False),
        ({"events": ["list", "retrieve"], "submissions": ["list", "retrieve"]}, False),
        ({"events": ["create"]}, True),
        ({"events": ["update"]}, True),
        ({"events": ["destroy"]}, True),
        ({"events": ["actions"]}, True),
        ({"events": ["list", "retrieve", "create"]}, True),
        ({"events": ["list", "retrieve"], "submissions": ["list", "update"]}, True),
    ),
    ids=[
        "empty",
        "empty_endpoint_list",
        "read_only_single",
        "read_only_multiple",
        "create",
        "update",
        "destroy",
        "actions",
        "mixed_single_endpoint",
        "mixed_multiple_endpoints",
    ],
)
def test_user_api_token_has_any_write_permission(endpoints, expected):
    token = UserApiToken(endpoints=endpoints)
    assert token.has_any_write_permission() is expected


@pytest.mark.parametrize(
    ("expires", "user_active", "expected"),
    (
        (None, True, True),
        ("future", True, True),
        ("past", True, False),
        (None, False, False),
    ),
    ids=["no_expiry", "future_expiry", "past_expiry", "inactive_user"],
)
@pytest.mark.django_db
def test_user_api_token_is_active(expires, user_active, expected):
    match expires:
        case "future":
            expires = tz_now() + dt.timedelta(days=1)
        case "past":
            expires = tz_now() - dt.timedelta(days=1)
    token = UserApiToken(expires=expires, user=UserFactory(is_active=user_active))
    assert token.is_active is expected


@pytest.mark.parametrize(
    ("version", "expected"),
    (
        (None, True),
        (CURRENT_VERSION, True),
        (DEV_PREVIEW, True),
        ("old-unsupported", False),
    ),
    ids=["no_version", "current", "dev_preview", "unsupported"],
)
def test_user_api_token_is_latest_version(version, expected):
    token = UserApiToken(version=version)
    assert token.is_latest_version is expected


@pytest.mark.django_db
def test_user_api_token_get_instance_data_lists_events_and_abbreviates_token():
    event = EventFactory()
    token = UserApiTokenFactory(limit_events=[event])

    data = token.get_instance_data()

    assert data["limit_events"] == [event.pk]
    assert data["all_events"] is False
    assert data["token"].endswith("…")
    assert token.token not in str(data)


@pytest.mark.django_db
def test_user_api_token_serialize():
    user = UserFactory()
    event = EventFactory()
    token = UserApiTokenFactory(
        user=user, name="Test Token", endpoints={"events": ["list"]}
    )
    token.limit_events.add(event)

    result = token.serialize()

    assert result == {
        "name": "Test Token",
        "token": f"{token.token[:4]}…",
        "all_events": False,
        "limit_events": [event.slug],
        "endpoints": {"events": ["list"]},
        "expires": None,
        "version": None,
    }

    expiry = tz_now()
    token.expires = expiry
    assert token.serialize()["expires"] == expiry.isoformat()


@pytest.mark.parametrize(
    ("endpoints", "expected_preset"),
    (
        ({ep: list(READ_PERMISSIONS) for ep in ENDPOINTS}, "read"),
        ({ep: list(WRITE_PERMISSIONS) for ep in ENDPOINTS}, "write"),
        ({}, "custom"),
        ({"events": ["list", "retrieve"], "submissions": ["list"]}, "custom"),
        ({ep: list(READ_PERMISSIONS) for ep in list(ENDPOINTS)[:-1]}, "custom"),
    ),
    ids=["read_all", "write_all", "empty", "partial", "missing_endpoint"],
)
def test_user_api_token_permission_preset(endpoints, expected_preset):
    token = UserApiToken(endpoints=endpoints)
    assert token.permission_preset == expected_preset


@pytest.mark.parametrize(
    ("endpoints", "expected"),
    (
        ({}, []),
        (
            {"events": ["list", "retrieve"]},
            [("/events", ["Read list", "Read details"])],
        ),
        (
            {"events": ["list"], "submissions": ["create", "update"]},
            [("/events", ["Read list"]), ("/submissions", ["Create", "Update"])],
        ),
    ),
    ids=["empty", "single_endpoint", "multiple_endpoints"],
)
def test_user_api_token_get_endpoint_permissions_display(endpoints, expected):
    token = UserApiToken(endpoints=endpoints)
    assert token.get_endpoint_permissions_display() == expected


def test_user_api_token_clean_requires_permissions():
    UserApiToken(endpoints={"events": ["list"]}).clean()
    with pytest.raises(ValidationError):
        UserApiToken(endpoints={}).clean()


@pytest.mark.django_db
def test_user_api_token_manager_active_excludes_expired_and_inactive_users():
    active = UserApiTokenFactory(expires=None)
    future = UserApiTokenFactory(expires=tz_now() + dt.timedelta(days=1))
    UserApiTokenFactory(expires=tz_now() - dt.timedelta(days=1))
    UserApiTokenFactory(user__is_active=False)

    assert set(UserApiToken.objects.active()) == {active, future}
