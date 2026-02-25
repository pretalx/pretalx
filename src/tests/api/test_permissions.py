from types import SimpleNamespace

import pytest
from django_scopes import scope, scopes_disabled

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

pytestmark = pytest.mark.unit


def make_view(action="list", detail=False, endpoint=None, permission_map=None):
    """Build a minimal view namespace with the attributes ApiPermission accesses.

    We use SimpleNamespace here rather than a real DRF ViewSet because the
    permission class only reads plain attributes (action, detail, endpoint,
    permission_map, queryset.model) — no methods or DRF request-dispatch
    machinery is involved, so a full ViewSet would add complexity without
    improving test fidelity.
    """
    return SimpleNamespace(
        action=action,
        detail=detail,
        endpoint=endpoint,
        permission_map=permission_map or {},
        queryset=SimpleNamespace(model=Event),
    )


@pytest.fixture
def orga_user():
    """An organiser, event, and user with a team granting can_change_event_settings."""
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


@pytest.mark.django_db
def test_api_permission_get_permission_object_returns_event_when_no_obj():
    event = EventFactory()
    request = make_api_request(event=event)

    result = ApiPermission().get_permission_object(view=None, obj=None, request=request)

    assert result == event


@pytest.mark.django_db
def test_api_permission_get_permission_object_returns_organiser_as_fallback():
    organiser = OrganiserFactory()
    request = make_api_request(organiser=organiser)

    result = ApiPermission().get_permission_object(view=None, obj=None, request=request)

    assert result == organiser


@pytest.mark.django_db
def test_api_permission_grants_with_team_permission(orga_user):
    """has_permission checks user.has_perm on the permission object."""
    view = make_view(permission_map={"list": "event.view_event"})
    request = make_api_request(user=orga_user.user, event=orga_user.event)

    assert ApiPermission().has_permission(request, view) is True


@pytest.mark.django_db
def test_api_permission_denies_anonymous_user():
    event = EventFactory()
    view = make_view(action="update", permission_map={"update": "event.update_event"})
    request = make_api_request(event=event)

    assert ApiPermission().has_permission(request, view) is False


@pytest.mark.django_db
def test_api_permission_detail_without_obj_returns_true_early():
    """On detail endpoints, DRF calls has_permission without an obj first;
    the permission should return True to let DRF proceed to has_object_permission."""
    view = make_view(action="retrieve", detail=True)
    request = make_api_request(user=UserFactory())

    assert ApiPermission()._has_permission(view, None, request) is True


@pytest.mark.django_db
def test_api_permission_has_object_permission_grants_admin_on_event(orga_user):
    user = UserFactory(is_administrator=True)
    view = make_view(
        action="retrieve", detail=True, permission_map={"retrieve": "event.view_event"}
    )
    request = make_api_request(user=user, event=orga_user.event)

    assert ApiPermission().has_object_permission(request, view, orga_user.event) is True


@pytest.mark.django_db
def test_api_permission_without_event_uses_organiser():
    organiser = OrganiserFactory()
    user = UserFactory(is_administrator=True)
    view = make_view(permission_map={"list": "event.view_organiser"})
    request = make_api_request(user=user, organiser=organiser)

    assert ApiPermission().has_permission(request, view) is True


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("action", "expected"),
    (("retrieve", True), ("custom_action", False)),
    ids=["known_action_uses_model_map", "unknown_action_denied"],
)
def test_api_permission_model_get_perm_fallback(action, expected):
    """When permission_map is empty, MODEL_PERMISSION_MAP maps the action before
    calling queryset.model.get_perm. Unknown actions pass through directly,
    producing an unregistered permission that denies access."""
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    user = UserFactory(is_administrator=True)
    view = make_view(action=action, permission_map={})
    request = make_api_request(user=user, event=event)

    assert ApiPermission().has_permission(request, view) is expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    "use_token",
    (
        pytest.param(True, id="endpoint_check"),
        pytest.param(False, id="permission_map_lookup"),
    ),
)
def test_api_permission_log_action_treated_as_retrieve(orga_user, use_token):
    """The 'log' action maps to 'retrieve' both for token endpoint checks
    and for permission_map lookups."""
    token = None
    if use_token:
        token = UserApiTokenFactory(user=orga_user.user)
        token.events.add(orga_user.event)
        token.endpoints = {"events": ["retrieve"]}
        token.save()

    view = make_view(
        action="log",
        endpoint="events" if use_token else None,
        permission_map={"retrieve": "event.view_event"},
    )
    request = make_api_request(user=orga_user.user, auth=token, event=orga_user.event)

    assert ApiPermission().has_permission(request, view) is True


@pytest.mark.django_db
def test_api_permission_with_token_denies_when_event_not_in_token():
    event = EventFactory()
    other_event = EventFactory()
    user = UserFactory()
    token = UserApiTokenFactory(user=user)
    token.events.add(other_event)

    view = make_view()
    request = make_api_request(user=user, auth=token, event=event)

    assert ApiPermission().has_permission(request, view) is False


@pytest.mark.django_db
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
    token = UserApiTokenFactory(user=orga_user.user)
    token.events.add(orga_user.event)
    token.endpoints = token_endpoints
    token.save()

    view = make_view(endpoint="events", permission_map={"list": "event.view_event"})
    request = make_api_request(user=orga_user.user, auth=token, event=orga_user.event)

    assert ApiPermission().has_permission(request, view) is expected


@pytest.mark.django_db
def test_api_permission_with_token_no_event_skips_event_checks():
    """When auth token is present but request has no event, the event-specific
    checks (event in token, reviewer check) are skipped entirely."""
    organiser = OrganiserFactory()
    user = UserFactory(is_administrator=True)
    token = UserApiTokenFactory(user=user)
    token.endpoints = {
        "events": ["list", "retrieve", "create", "update", "destroy", "actions"]
    }
    token.save()

    view = make_view(endpoint="events", permission_map={"list": "event.view_organiser"})
    request = make_api_request(user=user, auth=token, organiser=organiser)

    assert ApiPermission().has_permission(request, view) is True


@pytest.mark.django_db
def test_api_permission_with_token_no_endpoint_skips_endpoint_check(orga_user):
    """When auth token is present and event matches but view has no endpoint,
    the endpoint permission check is skipped."""
    token = UserApiTokenFactory(user=orga_user.user)
    token.events.add(orga_user.event)

    view = make_view(permission_map={"list": "event.view_event"})
    request = make_api_request(user=orga_user.user, auth=token, event=orga_user.event)

    assert ApiPermission().has_permission(request, view) is True


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("phase_kwargs", "expected"),
    (
        (None, False),
        ({"can_see_speaker_names": False}, False),
        ({"can_see_speaker_names": True}, True),
    ),
    ids=["no_active_phase", "phase_hides_speaker_names", "phase_shows_speaker_names"],
)
def test_api_permission_reviewer_only_with_review_phase(phase_kwargs, expected):
    """A reviewer-only user's API access depends on having an active review phase
    with can_see_speaker_names=True."""
    organiser = OrganiserFactory()
    event = EventFactory(organiser=organiser)
    user = UserFactory()
    team = TeamFactory(
        organiser=organiser,
        all_events=True,
        is_reviewer=True,
        can_change_submissions=False,
    )
    team.members.add(user)
    with scopes_disabled():
        event.review_phases.update(is_active=False)
        if phase_kwargs is not None:
            ReviewPhaseFactory(event=event, is_active=True, **phase_kwargs)
    token = UserApiTokenFactory(user=user)
    token.events.add(event)
    token.endpoints = {
        "events": ["list", "retrieve", "create", "update", "destroy", "actions"]
    }
    token.save()

    view = make_view(endpoint="events", permission_map={"list": "event.view_event"})
    request = make_api_request(user=user, auth=token, event=event)

    with scope(event=event):
        assert ApiPermission().has_permission(request, view) is expected


@pytest.mark.django_db
def test_plugin_permission_denies_when_no_event():
    view = SimpleNamespace(plugin_required="pretalx_test_plugin")
    request = make_api_request(user=UserFactory())

    assert PluginPermission().has_permission(request, view) is False


@pytest.mark.django_db
def test_plugin_permission_allows_when_no_plugin_required():
    event = EventFactory()
    view = SimpleNamespace(plugin_required=None)
    request = make_api_request(user=UserFactory(), event=event)

    assert PluginPermission().has_permission(request, view) is True


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("plugins", "expected"),
    (("pretalx_test_plugin", True), ("some_other_plugin", False)),
    ids=["plugin_active", "plugin_not_active"],
)
def test_plugin_permission_has_permission_with_plugin(plugins, expected):
    event = EventFactory()
    event.plugins = plugins
    event.save()

    view = SimpleNamespace(plugin_required="pretalx_test_plugin")
    request = make_api_request(user=UserFactory(), event=event)

    assert PluginPermission().has_permission(request, view) is expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("plugins", "expected"),
    (("pretalx_test_plugin", True), ("", False)),
    ids=["plugin_active", "plugin_not_active"],
)
def test_plugin_permission_has_object_permission(plugins, expected):
    event = EventFactory()
    if plugins:
        event.plugins = plugins
        event.save()

    view = SimpleNamespace(plugin_required="pretalx_test_plugin")
    request = make_api_request(user=UserFactory(), event=event)

    assert (
        PluginPermission().has_object_permission(request, view, obj=event) is expected
    )
