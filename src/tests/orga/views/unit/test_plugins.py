import types

import pytest
from django_scopes import scopes_disabled

from pretalx.common.plugins import get_all_plugins
from pretalx.orga.views.plugins import EventPluginsView
from tests.utils import make_orga_user, make_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_resolve_links_resolves_valid_url(event):
    """_resolve_links resolves URL names to actual URLs."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(EventPluginsView, request)
    plugin = next(p for p in get_all_plugins() if p.module == "tests.dummy_app")

    result = view._resolve_links(plugin, "settings_links")

    assert len(result) == 1
    url, label = result[0]
    assert url == f"/orga/event/{event.slug}/settings/"
    assert label == "Dummy Settings"


@pytest.mark.django_db
def test_resolve_links_skips_invalid_url(event):
    """_resolve_links silently skips URLs that cannot be resolved."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(EventPluginsView, request)
    plugin = types.SimpleNamespace(settings_links=[("Bad", "nonexistent:url.name", {})])

    result = view._resolve_links(plugin, "settings_links")

    assert result == []


@pytest.mark.django_db
def test_resolve_links_missing_attr_returns_empty(event):
    """_resolve_links returns empty list when plugin has no such attribute."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(EventPluginsView, request)
    plugin = next(p for p in get_all_plugins() if p.module == "tests.dummy_app")

    result = view._resolve_links(plugin, "nonexistent_links")

    assert result == []


@pytest.mark.django_db
def test_grouped_plugins_returns_dict_with_dummy_plugin(event):
    """grouped_plugins returns a dict keyed by category tuples, including the dummy plugin."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(EventPluginsView, request)

    result = view.grouped_plugins

    assert isinstance(result, dict)
    all_plugins = [p for plugins in result.values() for p in plugins]
    module_names = [p.module for p in all_plugins]
    assert "tests.dummy_app" in module_names
    for key in result:
        assert isinstance(key, tuple)
        assert len(key) == 2


@pytest.mark.django_db
def test_grouped_plugins_active_plugin_has_resolved_links(event):
    """Active plugins in grouped_plugins have their settings_links resolved."""
    with scopes_disabled():
        event.enable_plugin("tests.dummy_app")
        event.save()
        user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(EventPluginsView, request)

    grouped = view.grouped_plugins
    all_plugins = [p for plugins in grouped.values() for p in plugins]
    active = [p for p in all_plugins if p.module == "tests.dummy_app"]

    assert len(active) == 1
    assert len(active[0].resolved_settings_links) == 1
    url, label = active[0].resolved_settings_links[0]
    assert url == f"/orga/event/{event.slug}/settings/"
    assert label == "Dummy Settings"
    assert active[0].resolved_navigation_links == []


@pytest.mark.django_db
def test_grouped_plugins_inactive_plugin_has_empty_links(event):
    """Inactive plugins have empty resolved link lists."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(EventPluginsView, request)

    grouped = view.grouped_plugins
    all_plugins = [p for plugins in grouped.values() for p in plugins]
    inactive = [p for p in all_plugins if p.module == "tests.dummy_app"]

    assert len(inactive) == 1
    assert inactive[0].resolved_settings_links == []
    assert inactive[0].resolved_navigation_links == []


@pytest.mark.django_db
def test_plugins_active_returns_plugin_list(event):
    """plugins_active returns the event's current plugin list."""
    with scopes_disabled():
        event.enable_plugin("tests.dummy_app")
        event.save()
        user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(EventPluginsView, request)

    assert view.plugins_active == ["tests.dummy_app"]
