import datetime as dt

import pytest
from django.utils.timezone import now as tz_now

from pretalx.api.versions import CURRENT_VERSION, DEV_PREVIEW
from pretalx.person.models import UserApiToken
from pretalx.person.models.auth_token import (
    ENDPOINTS,
    READ_PERMISSIONS,
    WRITE_PERMISSIONS,
    generate_api_token,
)
from tests.factories import EventFactory, TeamFactory, UserApiTokenFactory, UserFactory

pytestmark = pytest.mark.unit


def test_generate_api_token_format():
    token = generate_api_token()
    assert len(token) == 64
    assert token.isalnum()
    assert token == token.lower()


def test_generate_api_token_unique():
    """Successive calls produce different tokens."""
    assert generate_api_token() != generate_api_token()


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
    ("expires", "expected"),
    ((None, True), ("future", True), ("past", False)),
    ids=["no_expiry", "future_expiry", "past_expiry"],
)
@pytest.mark.django_db
def test_user_api_token_is_active(expires, expected):
    if expires == "future":
        expires = tz_now() + dt.timedelta(days=1)
    elif expires == "past":
        expires = tz_now() - dt.timedelta(days=1)
    token = UserApiToken(expires=expires)
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
def test_user_api_token_serialize():
    user = UserFactory()
    event = EventFactory()
    token = UserApiTokenFactory(
        user=user, name="Test Token", endpoints={"events": ["list"]}
    )
    token.events.add(event)

    result = token.serialize()

    assert result["name"] == "Test Token"
    assert len(result["token"]) == 64
    assert result["events"] == [event.slug]
    assert result["endpoints"] == {"events": ["list"]}
    assert result["expires"] is None
    assert result["version"] is None


@pytest.mark.django_db
def test_user_api_token_serialize_with_expiry():
    token = UserApiTokenFactory()
    expiry = tz_now()
    token.expires = expiry
    token.save()

    result = token.serialize()

    assert result["expires"] == expiry.isoformat()


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


@pytest.mark.django_db
def test_user_api_token_manager_active_excludes_expired():
    user = UserFactory()
    active = UserApiTokenFactory(user=user, expires=None)
    UserApiTokenFactory(user=user, expires=tz_now() - dt.timedelta(days=1))

    result = list(UserApiToken.objects.active())

    assert result == [active]


@pytest.mark.django_db
def test_user_api_token_manager_active_includes_future():
    user = UserFactory()
    future = UserApiTokenFactory(user=user, expires=tz_now() + dt.timedelta(days=1))

    result = list(UserApiToken.objects.active())

    assert result == [future]


@pytest.mark.django_db
def test_user_api_token_update_events_removes_inaccessible():
    """When a user loses team access, events they can no longer reach are removed."""
    user = UserFactory()
    event1 = EventFactory()
    event2 = EventFactory()
    team = TeamFactory(organiser=event1.organiser, all_events=True)
    team.members.add(user)
    # event2 is on a different organiser, so user has no access
    token = UserApiTokenFactory(user=user)
    token.events.add(event1, event2)

    token.update_events()

    assert list(token.events.all()) == [event1]


@pytest.mark.django_db
def test_user_api_token_update_events_expires_when_all_removed():
    """Token is expired when all events are removed."""
    user = UserFactory()
    event = EventFactory()
    # User has no team membership, so no access to any events
    token = UserApiTokenFactory(user=user, expires=None)
    token.events.add(event)

    token.update_events()

    token.refresh_from_db()
    assert not token.events.exists()
    assert token.expires is not None
    assert token.expires <= tz_now()


@pytest.mark.django_db
def test_user_api_token_update_events_noop_when_all_accessible():
    """No changes when all events are still accessible."""
    user = UserFactory()
    event = EventFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True)
    team.members.add(user)
    token = UserApiTokenFactory(user=user)
    token.events.add(event)

    token.update_events()

    assert list(token.events.all()) == [event]
    token.refresh_from_db()
    assert token.expires is None
