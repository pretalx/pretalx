# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from types import SimpleNamespace

import pytest
from django_scopes import scope

from pretalx.api.permissions import ApiPermission, PluginPermission
from pretalx.event.models import Event
from tests.factories import (
    EventFactory,
    OrganiserFactory,
    ReviewPhaseFactory,
    TeamFactory,
    UserApiTokenFactory,
    UserFactory,
)
from tests.utils import make_api_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def make_view(action="list", detail=False, endpoint=None, permission_map=None):
    return SimpleNamespace(
        action=action,
        detail=detail,
        endpoint=endpoint,
        permission_map=permission_map or {},
        queryset=SimpleNamespace(model=Event),
    )


@pytest.fixture
def orga_user():
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    user = UserFactory()
    team = TeamFactory(
        organiser=organiser, all_events=True, can_change_event_settings=True
    )
    team.members.add(user)
    return SimpleNamespace(organiser=organiser, event=event, user=user, team=team)


def test_api_permission_get_permission_object_returns_obj_when_provided():
    obj = object()
    request = make_api_request()

    result = ApiPermission().get_permission_object(view=None, obj=obj, request=request)

    assert result is obj


def test_api_permission_get_permission_object_returns_event_when_no_obj():
    event = EventFactory()
    request = make_api_request(event=event)

    result = ApiPermission().get_permission_object(view=None, obj=None, request=request)

    assert result == event


def test_api_permission_get_permission_object_returns_organiser_as_fallback():
    organiser = OrganiserFactory()
    request = make_api_request(organiser=organiser)

    result = ApiPermission().get_permission_object(view=None, obj=None, request=request)

    assert result == organiser


def test_api_permission_grants_with_team_permission(orga_user):
    view = make_view(permission_map={"list": "event.view_event"})
    request = make_api_request(user=orga_user.user, event=orga_user.event)

    assert ApiPermission().has_permission(request, view) is True


def test_api_permission_denies_anonymous_user():
    event = EventFactory()
    view = make_view(action="update", permission_map={"update": "event.update_event"})
    request = make_api_request(event=event)

    assert ApiPermission().has_permission(request, view) is False


def test_api_permission_detail_without_obj_returns_true_early():
    view = make_view(action="retrieve", detail=True)
    request = make_api_request(user=UserFactory())

    assert ApiPermission()._has_permission(view, None, request) is True


def test_api_permission_has_object_permission_grants_admin_on_event(orga_user):
    user = UserFactory(is_administrator=True)
    view = make_view(
        action="retrieve", detail=True, permission_map={"retrieve": "event.view_event"}
    )
    request = make_api_request(user=user, event=orga_user.event)

    assert ApiPermission().has_object_permission(request, view, orga_user.event) is True


def test_api_permission_without_event_uses_organiser():
    organiser = OrganiserFactory()
    user = UserFactory(is_administrator=True)
    view = make_view(permission_map={"list": "event.view_organiser"})
    request = make_api_request(user=user, organiser=organiser)

    assert ApiPermission().has_permission(request, view) is True


@pytest.mark.parametrize(
    ("action", "expected"),
    (("retrieve", True), ("custom_action", False)),
    ids=["known_action_uses_model_map", "unknown_action_denied"],
)
def test_api_permission_model_get_perm_fallback(action, expected):
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    user = UserFactory(is_administrator=True)
    view = make_view(action=action, permission_map={})
    request = make_api_request(user=user, event=event)

    assert ApiPermission().has_permission(request, view) is expected


@pytest.mark.parametrize(
    "use_token",
    (
        pytest.param(True, id="endpoint_check"),
        pytest.param(False, id="permission_map_lookup"),
    ),
)
def test_api_permission_log_action_treated_as_retrieve(orga_user, use_token):
    token = None
    if use_token:
        token = UserApiTokenFactory(
            user=orga_user.user,
            limit_events=[orga_user.event],
            endpoints={"events": ["retrieve"]},
        )

    view = make_view(
        action="log",
        endpoint="events" if use_token else None,
        permission_map={"retrieve": "event.view_event"},
    )
    request = make_api_request(user=orga_user.user, auth=token, event=orga_user.event)

    assert ApiPermission().has_permission(request, view) is True


def test_api_permission_with_token_denies_when_event_not_in_token():
    event = EventFactory()
    other_event = EventFactory()
    user = UserFactory()
    token = UserApiTokenFactory(user=user, limit_events=[other_event])

    view = make_view()
    request = make_api_request(user=user, auth=token, event=event)

    assert ApiPermission().has_permission(request, view) is False


def test_api_permission_all_events_token_skips_event_scope_check(orga_user):
    token = UserApiTokenFactory(
        user=orga_user.user, all_events=True, endpoints={"events": ["list"]}
    )
    new_event = EventFactory(organiser=orga_user.organiser)

    view = make_view(endpoint="events", permission_map={"list": "event.view_event"})
    request = make_api_request(user=orga_user.user, auth=token, event=new_event)

    assert ApiPermission().has_permission(request, view) is True


@pytest.mark.parametrize(
    ("token_endpoints", "expected"),
    (
        (
            {"events": ["list", "retrieve", "create", "update", "destroy", "actions"]},
            True,
        ),
        ({"events": ["retrieve"]}, False),
    ),
    ids=["endpoint_allowed", "endpoint_denied"],
)
def test_api_permission_with_token_endpoint_check(orga_user, token_endpoints, expected):
    token = UserApiTokenFactory(
        user=orga_user.user, limit_events=[orga_user.event], endpoints=token_endpoints
    )

    view = make_view(endpoint="events", permission_map={"list": "event.view_event"})
    request = make_api_request(user=orga_user.user, auth=token, event=orga_user.event)

    assert ApiPermission().has_permission(request, view) is expected


@pytest.mark.parametrize(
    ("scope", "expected"),
    (("all_events", True), ("full_selection", True), ("subset", False)),
    ids=["all_events_token", "token_covers_all_events", "token_scoped_to_subset"],
)
def test_api_permission_token_organiser_scope(scope, expected):
    organiser = OrganiserFactory()
    event_a = EventFactory(organiser=organiser)
    event_b = EventFactory(organiser=organiser)
    user = UserFactory(is_administrator=True)
    token = UserApiTokenFactory(
        user=user,
        all_events=scope == "all_events",
        limit_events={
            "all_events": [],
            "full_selection": [event_a, event_b],
            "subset": [event_a],
        }[scope],
        endpoints={"teams": ["list", "retrieve"]},
    )

    view = make_view(endpoint="teams", permission_map={"list": "event.view_organiser"})
    request = make_api_request(user=user, auth=token, organiser=organiser)

    assert ApiPermission().has_permission(request, view) is expected


@pytest.mark.parametrize(
    ("all_events", "expected"),
    ((False, False), (True, True)),
    ids=["limited_token_denied", "all_events_token_allowed"],
)
def test_api_permission_token_organiser_scope_empty_organiser(all_events, expected):
    organiser = OrganiserFactory()
    other_event = EventFactory()  # belongs to a different organiser
    user = UserFactory(is_administrator=True)
    token = UserApiTokenFactory(
        user=user,
        all_events=all_events,
        limit_events=[] if all_events else [other_event],
        endpoints={"teams": ["list", "retrieve"]},
    )

    view = make_view(endpoint="teams", permission_map={"list": "event.view_organiser"})
    request = make_api_request(user=user, auth=token, organiser=organiser)

    assert ApiPermission().has_permission(request, view) is expected


def test_api_permission_with_token_no_event_no_organiser_skips_scope_checks():
    user = UserFactory()
    token = UserApiTokenFactory(user=user)

    view = make_view(action="retrieve", detail=True)
    request = make_api_request(user=user, auth=token)

    assert ApiPermission()._has_permission(view, None, request) is True


def test_api_permission_with_token_no_endpoint_skips_endpoint_check(orga_user):
    token = UserApiTokenFactory(user=orga_user.user, limit_events=[orga_user.event])

    view = make_view(permission_map={"list": "event.view_event"})
    request = make_api_request(user=orga_user.user, auth=token, event=orga_user.event)

    assert ApiPermission().has_permission(request, view) is True


@pytest.mark.parametrize(
    ("team_kwargs", "phase_kwargs", "expected"),
    (
        ({}, None, False),
        ({}, {"can_see_speaker_names": False}, False),
        ({}, {"can_see_speaker_names": True}, True),
        (
            {"force_hide_speaker_names": True, "can_change_event_settings": True},
            {"can_see_speaker_names": True},
            False,
        ),
    ),
    ids=[
        "no_active_phase",
        "phase_hides_speaker_names",
        "phase_shows_speaker_names",
        "force_hide_overrides_with_extra_permission",
    ],
)
def test_api_permission_reviewer_only_with_review_phase(
    team_kwargs, phase_kwargs, expected
):
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    user = UserFactory()
    team = TeamFactory(
        organiser=organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=False,
        **team_kwargs,
    )
    team.members.add(user)
    event.review_phases.update(is_active=False)
    if phase_kwargs is not None:
        ReviewPhaseFactory(event=event, is_active=True, **phase_kwargs)
    token = UserApiTokenFactory(
        user=user,
        limit_events=[event],
        endpoints={
            "events": ["list", "retrieve", "create", "update", "destroy", "actions"]
        },
    )

    view = make_view(endpoint="events", permission_map={"list": "event.view_event"})
    request = make_api_request(user=user, auth=token, event=event)

    with scope(event=event):
        assert ApiPermission().has_permission(request, view) is expected


def test_plugin_permission_denies_when_no_event():
    view = SimpleNamespace(plugin_required="pretalx_test_plugin")
    request = make_api_request(user=UserFactory())

    assert PluginPermission().has_permission(request, view) is False


def test_plugin_permission_allows_when_no_plugin_required():
    event = EventFactory()
    view = SimpleNamespace(plugin_required=None)
    request = make_api_request(user=UserFactory(), event=event)

    assert PluginPermission().has_permission(request, view) is True


@pytest.mark.parametrize(
    ("plugins", "expected"),
    (("pretalx_test_plugin", True), ("some_other_plugin", False)),
    ids=["plugin_active", "plugin_not_active"],
)
def test_plugin_permission_has_permission_with_plugin(plugins, expected):
    event = EventFactory(plugins=plugins)

    view = SimpleNamespace(plugin_required="pretalx_test_plugin")
    request = make_api_request(user=UserFactory(), event=event)

    assert PluginPermission().has_permission(request, view) is expected


@pytest.mark.parametrize(
    ("plugins", "expected"),
    (("pretalx_test_plugin", True), ("", False)),
    ids=["plugin_active", "plugin_not_active"],
)
def test_plugin_permission_has_object_permission(plugins, expected):
    event = EventFactory(plugins=plugins)

    view = SimpleNamespace(plugin_required="pretalx_test_plugin")
    request = make_api_request(user=UserFactory(), event=event)

    assert (
        PluginPermission().has_object_permission(request, view, obj=event) is expected
    )
