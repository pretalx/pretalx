# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.person.interfaces.forms import AuthTokenForm
from pretalx.person.interfaces.forms.auth_token import AuthTokenUpdateForm
from pretalx.person.models.auth_token import (
    ENDPOINTS,
    READ_PERMISSIONS,
    WRITE_PERMISSIONS,
)
from tests.factories import EventFactory, UserApiTokenFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _build_form_data(event, preset="read"):
    """Build minimal valid form data for AuthTokenForm."""
    data = {
        "name": "My Token",
        "limit_events": [event.pk],
        "expires": "",
        "permission_preset": preset,
    }
    if preset == "custom":
        for endpoint in ENDPOINTS:
            data[f"endpoint_{endpoint}"] = READ_PERMISSIONS
    return data


def test_auth_token_form_init_events_queryset_limited_to_user_events(user_with_event):
    user, event = user_with_event
    EventFactory()  # event the user has no access to

    form = AuthTokenForm(user=user)

    assert list(form.fields["limit_events"].queryset) == [event]


def test_auth_token_form_init_creates_endpoint_fields(user_with_event):
    """Form init creates a checkbox field for each endpoint, defaulting to read."""
    user, _ = user_with_event

    form = AuthTokenForm(user=user)

    for endpoint in ENDPOINTS:
        field_name = f"endpoint_{endpoint}"
        assert field_name in form.fields
        assert form.fields[field_name].label == f"/{endpoint}"
        assert form.fields[field_name].initial == READ_PERMISSIONS


def test_auth_token_form_get_endpoint_fields_returns_bound_fields(user_with_event):
    """get_endpoint_fields() returns (name, BoundField) pairs for templates."""
    user, _ = user_with_event
    form = AuthTokenForm(user=user)

    endpoint_fields = form.get_endpoint_fields()

    assert len(endpoint_fields) == len(ENDPOINTS)
    for field_name, bound_field in endpoint_fields:
        assert field_name.startswith("endpoint_")
        assert bound_field.name == field_name


@pytest.mark.parametrize(
    ("preset", "expected_permissions"),
    (("read", list(READ_PERMISSIONS)), ("write", list(WRITE_PERMISSIONS))),
)
def test_auth_token_form_clean_preset_sets_permissions(
    user_with_event, preset, expected_permissions
):
    user, event = user_with_event
    data = _build_form_data(event, preset=preset)

    form = AuthTokenForm(data=data, user=user)
    assert form.is_valid(), form.errors

    for endpoint in ENDPOINTS:
        assert form.instance.endpoints[endpoint] == expected_permissions


def test_auth_token_form_clean_custom_preset_rejects_no_permissions(user_with_event):
    user, event = user_with_event
    data = _build_form_data(event, preset="custom")
    for endpoint in ENDPOINTS:
        data[f"endpoint_{endpoint}"] = []

    form = AuthTokenForm(data=data, user=user)

    assert not form.is_valid()


def test_auth_token_form_clean_custom_preset_uses_per_endpoint_selections(
    user_with_event,
):
    user, event = user_with_event
    data = _build_form_data(event, preset="custom")
    data["endpoint_teams"] = ["list", "retrieve", "create"]
    data["endpoint_events"] = ["list"]

    form = AuthTokenForm(data=data, user=user)
    assert form.is_valid(), form.errors

    assert form.instance.endpoints["teams"] == ["list", "retrieve", "create"]
    assert form.instance.endpoints["events"] == ["list"]


def test_auth_token_form_save_sets_user_and_endpoints(user_with_event):
    user, event = user_with_event
    data = _build_form_data(event, preset="read")

    form = AuthTokenForm(data=data, user=user)
    assert form.is_valid(), form.errors

    token = form.save()

    assert token.user == user
    assert token.name == "My Token"
    assert token.endpoints == {
        endpoint: list(READ_PERMISSIONS) for endpoint in ENDPOINTS
    }
    assert token.pk is not None


def test_auth_token_form_save_associates_events(user_with_event):
    user, event = user_with_event
    data = _build_form_data(event, preset="read")

    form = AuthTokenForm(data=data, user=user)
    assert form.is_valid(), form.errors

    token = form.save()

    assert list(token.limit_events.all()) == [event]
    assert token.all_events is False


def test_auth_token_form_all_events_needs_no_limit_events(user_with_event):
    user, event = user_with_event
    data = _build_form_data(event, preset="read")
    data["limit_events"] = []
    data["all_events"] = "on"

    form = AuthTokenForm(data=data, user=user)
    assert form.is_valid(), form.errors

    token = form.save()

    assert token.all_events is True
    assert list(token.limit_events.all()) == []


def test_auth_token_form_all_events_clears_submitted_limit_events(user_with_event):
    user, event = user_with_event
    data = _build_form_data(event, preset="read")
    data["all_events"] = "on"

    form = AuthTokenForm(data=data, user=user)
    assert form.is_valid(), form.errors

    token = form.save()

    assert token.all_events is True
    assert list(token.limit_events.all()) == []


def test_auth_token_form_rejects_missing_event_scope(user_with_event):
    user, event = user_with_event
    data = _build_form_data(event, preset="read")
    data["limit_events"] = []

    form = AuthTokenForm(data=data, user=user)

    assert not form.is_valid()
    assert "limit_events" in form.errors
    assert "__all__" not in form.errors


def test_auth_token_form_invalid_limit_events_gets_single_error(user_with_event):
    user, event = user_with_event
    inaccessible_event = EventFactory()
    data = _build_form_data(event, preset="read")
    data["limit_events"] = [inaccessible_event.pk]

    form = AuthTokenForm(data=data, user=user)

    assert not form.is_valid()
    assert len(form.errors["limit_events"]) == 1


def test_auth_token_update_form_adds_events(user_with_event):
    user, event = user_with_event
    second_event = EventFactory(organiser=event.organiser)
    token = UserApiTokenFactory(
        user=user, limit_events=[event], endpoints={"events": ["list"]}
    )

    form = AuthTokenUpdateForm(
        data={"limit_events": [event.pk, second_event.pk]}, user=user, instance=token
    )
    assert form.is_valid(), form.errors
    form.save()

    assert set(token.limit_events.all()) == {event, second_event}
    assert token.all_events is False


def test_auth_token_update_form_switches_to_all_events(user_with_event):
    user, event = user_with_event
    token = UserApiTokenFactory(
        user=user, limit_events=[event], endpoints={"events": ["list"]}
    )

    form = AuthTokenUpdateForm(data={"all_events": "on"}, user=user, instance=token)
    assert form.is_valid(), form.errors
    form.save()

    token.refresh_from_db()
    assert token.all_events is True


def test_auth_token_update_form_all_events_clears_submitted_limit_events(
    user_with_event,
):
    user, event = user_with_event
    token = UserApiTokenFactory(
        user=user, limit_events=[event], endpoints={"events": ["list"]}
    )

    form = AuthTokenUpdateForm(
        data={"all_events": "on", "limit_events": [event.pk]}, user=user, instance=token
    )
    assert form.is_valid(), form.errors
    form.save()

    token.refresh_from_db()
    assert token.all_events is True
    assert list(token.limit_events.all()) == []


def test_auth_token_update_form_queryset_limited_to_user_events(user_with_event):
    user, event = user_with_event
    EventFactory()  # event the user has no access to
    token = UserApiTokenFactory(
        user=user, limit_events=[event], endpoints={"events": ["list"]}
    )

    form = AuthTokenUpdateForm(user=user, instance=token)

    assert list(form.fields["limit_events"].queryset) == [event]


def test_auth_token_update_form_rejects_missing_event_scope(user_with_event):
    user, event = user_with_event
    token = UserApiTokenFactory(
        user=user, limit_events=[event], endpoints={"events": ["list"]}
    )

    form = AuthTokenUpdateForm(data={"limit_events": []}, user=user, instance=token)

    assert not form.is_valid()
    assert "limit_events" in form.errors
