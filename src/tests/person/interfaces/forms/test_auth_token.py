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


def test_auth_token_form_init_limits_events_and_builds_endpoint_fields(user_with_event):
    user, event = user_with_event
    EventFactory()  # event the user has no access to

    form = AuthTokenForm(user=user)

    assert list(form.fields["limit_events"].queryset) == [event]
    for endpoint in ENDPOINTS:
        field_name = f"endpoint_{endpoint}"
        assert field_name in form.fields
        assert form.fields[field_name].label == f"/{endpoint}"
        assert form.fields[field_name].initial == READ_PERMISSIONS
    assert [(name, bound.name) for name, bound in form.get_endpoint_fields()] == [
        (f"endpoint_{endpoint}",) * 2 for endpoint in ENDPOINTS
    ]


@pytest.mark.parametrize(
    ("preset", "expected_permissions"),
    (("read", list(READ_PERMISSIONS)), ("write", list(WRITE_PERMISSIONS))),
)
def test_auth_token_form_preset_save_sets_user_endpoints_and_events(
    user_with_event, preset, expected_permissions
):
    user, event = user_with_event
    data = _build_form_data(event, preset=preset)

    form = AuthTokenForm(data=data, user=user)
    assert form.is_valid(), form.errors
    token = form.save()

    assert token.pk is not None
    assert token.user == user
    assert token.name == "My Token"
    assert token.endpoints == dict.fromkeys(ENDPOINTS, expected_permissions)
    assert list(token.limit_events.all()) == [event]
    assert token.all_events is False


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


@pytest.mark.parametrize("with_limit_events", (False, True))
def test_auth_token_form_all_events_ignores_limit_events(
    user_with_event, with_limit_events
):
    user, event = user_with_event
    data = _build_form_data(event, preset="read")
    data["limit_events"] = [event.pk] if with_limit_events else []
    data["all_events"] = "on"

    form = AuthTokenForm(data=data, user=user)
    assert form.is_valid(), form.errors

    token = form.save()

    assert token.all_events is True
    assert list(token.limit_events.all()) == []


def test_auth_token_form_limit_events_errors(user_with_event):
    user, event = user_with_event
    inaccessible_event = EventFactory()
    data = _build_form_data(event, preset="read")

    missing = AuthTokenForm(data=data | {"limit_events": []}, user=user)
    inaccessible = AuthTokenForm(
        data=data | {"limit_events": [inaccessible_event.pk]}, user=user
    )

    assert not missing.is_valid()
    assert list(missing.errors) == ["limit_events"]
    assert not inaccessible.is_valid()
    assert list(inaccessible.errors) == ["limit_events"]
    assert len(inaccessible.errors["limit_events"]) == 1


def test_auth_token_update_form_limits_queryset_and_adds_events(user_with_event):
    user, event = user_with_event
    second_event = EventFactory(organiser=event.organiser)
    EventFactory()  # event the user has no access to
    token = UserApiTokenFactory(
        user=user, limit_events=[event], endpoints={"events": ["list"]}
    )

    form = AuthTokenUpdateForm(user=user, instance=token)
    assert set(form.fields["limit_events"].queryset) == {event, second_event}

    form = AuthTokenUpdateForm(
        data={"limit_events": [event.pk, second_event.pk]}, user=user, instance=token
    )
    assert form.is_valid(), form.errors
    form.save()

    assert set(token.limit_events.all()) == {event, second_event}
    assert token.all_events is False


@pytest.mark.parametrize("with_limit_events", (False, True))
def test_auth_token_update_form_switches_to_all_events(
    user_with_event, with_limit_events
):
    user, event = user_with_event
    token = UserApiTokenFactory(
        user=user, limit_events=[event], endpoints={"events": ["list"]}
    )
    data = {"all_events": "on"}
    if with_limit_events:
        data["limit_events"] = [event.pk]

    form = AuthTokenUpdateForm(data=data, user=user, instance=token)
    assert form.is_valid(), form.errors
    form.save()

    token.refresh_from_db()
    assert token.all_events is True
    assert list(token.limit_events.all()) == []


def test_auth_token_update_form_rejects_missing_event_scope(user_with_event):
    user, event = user_with_event
    token = UserApiTokenFactory(
        user=user, limit_events=[event], endpoints={"events": ["list"]}
    )

    form = AuthTokenUpdateForm(data={"limit_events": []}, user=user, instance=token)

    assert not form.is_valid()
    assert "limit_events" in form.errors
