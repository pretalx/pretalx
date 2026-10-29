# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.test import override_settings

from pretalx.common.plugins import (
    get_all_plugins,
    get_all_plugins_grouped,
    plugin_group_key,
    plugin_sort_key,
)
from tests.dummy_app import PluginApp
from tests.dummy_app_no_hooks.apps import PluginApp as NoHooksPluginApp

pytestmark = pytest.mark.unit


def test_get_all_plugins_sets_plugin_metadata():
    plugins = get_all_plugins()

    assert plugins == [PluginApp.PretalxPluginMeta, NoHooksPluginApp.PretalxPluginMeta]
    dummy = plugins[0]
    assert dummy.module == "tests.dummy_app"
    assert dummy.app.name == "tests.dummy_app"
    assert dummy.highlighted is False


@pytest.mark.parametrize("available", (True, False))
def test_get_all_plugins_filters_by_event_availability(available):

    class FakeEvent:
        _dummy_available = available

    plugins = get_all_plugins(event=FakeEvent())

    assert (PluginApp.PretalxPluginMeta in plugins) is available


def test_get_all_plugins_sorted_highlighted_first():
    with override_settings(HIGHLIGHTED_PLUGINS=["tests.dummy_app_no_hooks"]):
        plugins = get_all_plugins()
        grouped = get_all_plugins_grouped()

    assert plugins == [NoHooksPluginApp.PretalxPluginMeta, PluginApp.PretalxPluginMeta]
    assert plugins[0].highlighted is True
    assert grouped == {("OTHER", "Other"): plugins}


@pytest.mark.parametrize(
    ("first_attrs", "second_attrs"),
    (
        (
            {"highlighted": True, "name": "ZZZ Plugin"},
            {"highlighted": False, "name": "AAA Plugin"},
        ),
        (
            {"highlighted": False, "name": "Alpha Plugin"},
            {"highlighted": False, "name": "Zeta Plugin"},
        ),
    ),
    ids=("highlighted_before_non_highlighted", "alphabetical_within_same_highlight"),
)
def test_plugin_sort_key_ordering(first_attrs, second_attrs):
    first = type("Plugin", (), first_attrs)()
    second = type("Plugin", (), second_attrs)()

    assert plugin_sort_key(first) < plugin_sort_key(second)


def test_plugin_sort_key_strips_pretalx_prefix():
    with_prefix = type("Plugin", (), {"highlighted": False, "name": "pretalx Foo"})()
    without_prefix = type("Plugin", (), {"highlighted": False, "name": "Foo"})()

    assert plugin_sort_key(with_prefix) == plugin_sort_key(without_prefix)


@pytest.mark.parametrize(
    ("attrs", "expected"),
    (({"category": "FEATURE"}, "FEATURE"), ({}, "OTHER")),
    ids=("with_category", "default"),
)
def test_plugin_group_key(attrs, expected):
    plugin_cls = type("Plugin", (), attrs)

    assert plugin_group_key(plugin_cls()) == expected


@pytest.mark.parametrize("filter_visible", (True, False))
def test_get_all_plugins_grouped(filter_visible):
    result = get_all_plugins_grouped(filter_visible=filter_visible)

    assert result == {
        ("OTHER", "Other"): [
            PluginApp.PretalxPluginMeta,
            NoHooksPluginApp.PretalxPluginMeta,
        ]
    }
