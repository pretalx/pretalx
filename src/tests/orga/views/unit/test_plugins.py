# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import types

import pytest

from pretalx.common.plugins import get_all_plugins
from pretalx.event.domain.plugins import enable_plugin
from pretalx.orga.views.plugins import EventPluginsView
from tests.utils import make_orga_user, make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _dummy_plugin(view):
    grouped = view.grouped_plugins
    assert dict(grouped.keys())["OTHER"] == "Other"
    return next(
        plugin
        for (category, _label), plugins in grouped.items()
        if category == "OTHER"
        for plugin in plugins
        if plugin.module == "tests.dummy_app"
    )


def test_resolve_links(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(EventPluginsView, request)
    plugin = next(p for p in get_all_plugins() if p.module == "tests.dummy_app")
    broken = types.SimpleNamespace(settings_links=[("Bad", "nonexistent:url.name", {})])

    assert view._resolve_links(plugin, "settings_links") == [
        (f"/orga/event/{event.slug}/settings/", "Dummy Settings")
    ]
    assert view._resolve_links(plugin, "nonexistent_links") == []
    assert view._resolve_links(broken, "settings_links") == []


def test_grouped_plugins_inactive_plugin_has_empty_links(event):
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(EventPluginsView, request)

    plugin = _dummy_plugin(view)

    assert view.plugins_active == []
    assert plugin.resolved_settings_links == []
    assert plugin.resolved_navigation_links == []


def test_grouped_plugins_active_plugin_has_resolved_links(event):
    enable_plugin(event, "tests.dummy_app")
    user = make_orga_user(event, can_change_event_settings=True)
    request = make_request(event, user=user)
    view = make_view(EventPluginsView, request)

    plugin = _dummy_plugin(view)

    assert view.plugins_active == ["tests.dummy_app"]
    assert plugin.resolved_settings_links == [
        (f"/orga/event/{event.slug}/settings/", "Dummy Settings")
    ]
    assert plugin.resolved_navigation_links == []
