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


def test_apply_plugin_changes_persists_and_calls_installed_and_uninstalled_hooks(event):
    installed_events.clear()
    uninstalled_events.clear()
    event.plugins = ""
    event.save(update_fields=["plugins"])

    apply_plugin_changes(event, ["tests.dummy_app"])

    assert installed_events == [event.slug]
    assert uninstalled_events == []
    event.refresh_from_db()
    assert event.plugin_list == ["tests.dummy_app"]

    apply_plugin_changes(event, [])

    assert installed_events == [event.slug]
    assert uninstalled_events == [event.slug]
    event.refresh_from_db()
    assert event.plugin_list == []


def test_apply_plugin_changes_skips_missing_hooks_and_unchanged_targets(event):
    apply_plugin_changes(event, ["tests.dummy_app_no_hooks"])
    assert event.plugin_list == ["tests.dummy_app_no_hooks"]
    updated = event.updated

    apply_plugin_changes(event, ["tests.dummy_app_no_hooks"])
    assert event.updated == updated

    apply_plugin_changes(event, [])
    assert event.plugin_list == []


def test_apply_plugin_changes_drops_unknown_new_modules_but_keeps_active_ones(event):
    event.plugins = "ghost.plugin"

    apply_plugin_changes(
        event, ["ghost.plugin", "tests.dummy_app", "totally.unknown.module"]
    )

    assert set(event.plugin_list) == {"ghost.plugin", "tests.dummy_app"}


def test_apply_plugin_changes_enables_invisible_plugin(event, monkeypatch):
    monkeypatch.setattr(PluginApp.PretalxPluginMeta, "visible", False)
    event.plugins = ""
    apply_plugin_changes(event, ["tests.dummy_app"])
    assert event.plugin_list == ["tests.dummy_app"]


def test_enable_and_disable_plugin_are_idempotent(event):
    event.plugins = ""

    disable_plugin(event, "tests.dummy_app")
    assert event.plugin_list == []

    enable_plugin(event, "tests.dummy_app")
    enable_plugin(event, "tests.dummy_app")
    assert event.plugin_list == ["tests.dummy_app"]

    disable_plugin(event, "tests.dummy_app")
    assert event.plugin_list == []
