# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.test import override_settings

from pretalx.common.plugins import get_all_plugins, get_all_plugins_grouped
from tests.dummy_app import PluginApp


@pytest.mark.django_db
def test_get_all_plugins():
    assert PluginApp.PretalxPluginMeta in get_all_plugins(), get_all_plugins()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("event", "expected"), ((None, True), ("hidden", True), ("totally hidden", False))
)
def test_get_all_plugins_with_event(event, expected):
    assert (PluginApp.PretalxPluginMeta in get_all_plugins(event)) is expected


@pytest.mark.django_db
def test_plugins_have_highlighted_attribute():
    plugins = get_all_plugins()
    for plugin in plugins:
        assert hasattr(plugin, "highlighted")


@pytest.mark.django_db
def test_highlighted_plugins_sorted_first():
    with override_settings(HIGHLIGHTED_PLUGINS=["tests"]):
        plugins = get_all_plugins()
        assert plugins[0].highlighted
        plugins = get_all_plugins_grouped()
        other_plugins = list(plugins.values())[-1]
        assert other_plugins[0].highlighted
