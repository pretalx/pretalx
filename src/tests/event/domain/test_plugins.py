# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.event.domain.plugins import (
    apply_plugin_changes,
    disable_plugin,
    enable_plugin,
)
from tests.dummy_app.apps import PluginApp, installed_events, uninstalled_events

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_apply_plugin_changes_calls_installed_hook(event):
    installed_events.clear()
    apply_plugin_changes(event, ["tests.dummy_app"])
    assert installed_events == [event.slug]


def test_apply_plugin_changes_calls_uninstalled_hook(event):
    uninstalled_events.clear()
    event.plugins = "tests.dummy_app"
    apply_plugin_changes(event, [])
    assert uninstalled_events == [event.slug]


def test_apply_plugin_changes_skips_missing_installed_hook(event):
    """Enabling a plugin whose app has no installed() method doesn't error."""
    apply_plugin_changes(event, ["tests.dummy_app_no_hooks"])
    assert event.plugin_list == ["tests.dummy_app_no_hooks"]


def test_apply_plugin_changes_skips_missing_uninstalled_hook(event):
    """Disabling a plugin whose app has no uninstalled() method doesn't error."""
    event.plugins = "tests.dummy_app_no_hooks"
    apply_plugin_changes(event, [])
    assert event.plugin_list == []


def test_apply_plugin_changes_persists_to_db(event):
    """The function writes event.plugins and saves it."""
    event.plugins = ""
    event.save(update_fields=["plugins"])
    apply_plugin_changes(event, ["tests.dummy_app"])
    event.refresh_from_db()
    assert event.plugin_list == ["tests.dummy_app"]


def test_apply_plugin_changes_drops_unknown_new_modules(event):
    """Unknown additions that are not currently active are silently dropped."""
    event.plugins = ""
    apply_plugin_changes(event, ["totally.unknown.module"])
    assert event.plugin_list == []


def test_apply_plugin_changes_preserves_active_unavailable_modules(event):
    """Modules already on the event that are no longer available are kept."""
    event.plugins = "ghost.plugin"
    apply_plugin_changes(event, ["ghost.plugin", "tests.dummy_app"])
    assert set(event.plugin_list) == {"ghost.plugin", "tests.dummy_app"}


def test_apply_plugin_changes_enables_invisible_plugin(event, monkeypatch):
    """Invisible plugins (visible = False) can still be enabled.

    Visibility only controls whether a plugin is listed in the UI, not
    whether it may be active for an event.
    """
    monkeypatch.setattr(PluginApp.PretalxPluginMeta, "visible", False)
    event.plugins = ""
    apply_plugin_changes(event, ["tests.dummy_app"])
    assert event.plugin_list == ["tests.dummy_app"]


def test_enable_plugin_adds_to_list(event):
    event.plugins = ""
    enable_plugin(event, "tests.dummy_app")
    assert event.plugin_list == ["tests.dummy_app"]


def test_enable_plugin_twice_is_idempotent(event):
    enable_plugin(event, "tests.dummy_app")
    enable_plugin(event, "tests.dummy_app")
    assert event.plugin_list.count("tests.dummy_app") == 1


def test_disable_plugin_removes_from_list(event):
    event.plugins = ""
    enable_plugin(event, "tests.dummy_app")
    assert event.plugin_list == ["tests.dummy_app"]

    disable_plugin(event, "tests.dummy_app")
    assert event.plugin_list == []


def test_disable_plugin_not_present_is_noop(event):
    event.plugins = ""
    disable_plugin(event, "nonexistent")
    assert event.plugin_list == []
