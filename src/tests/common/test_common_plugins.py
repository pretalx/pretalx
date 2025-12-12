# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.common.plugins import get_all_plugins, get_all_plugins_grouped
from tests.dummy_app import PluginApp


@pytest.mark.django_db
def test_get_all_plugins():
    assert PluginApp.PretalxPluginMeta in get_all_plugins(), get_all_plugins()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "event,expected", ((None, True), ("hidden", True), ("totally hidden", False))
)
def test_get_all_plugins_with_event(event, expected):
    assert (PluginApp.PretalxPluginMeta in get_all_plugins(event)) is expected


@pytest.mark.django_db
def test_plugins_have_highlighted_attribute():
    plugins = get_all_plugins()
    for plugin in plugins:
        assert hasattr(plugin, "highlighted")


@pytest.mark.django_db
def test_highlighted_plugins_sorted_first(settings):
    settings.HIGHLIGHTED_PLUGINS = ["tests"]
    plugins = get_all_plugins()
    highlighted_plugins = [p for p in plugins if p.highlighted]
    non_highlighted_plugins = [p for p in plugins if not p.highlighted]
    assert highlighted_plugins
    # All highlighted plugins should come before non-highlighted ones
    for hp in highlighted_plugins:
        for nhp in non_highlighted_plugins:
            assert plugins.index(hp) < plugins.index(nhp)


@pytest.mark.django_db
def test_highlighted_plugins_sorted_first_in_groups(settings):
    settings.HIGHLIGHTED_PLUGINS = ["tests"]
    grouped = get_all_plugins_grouped()
    for _category, plugins in grouped.items():
        highlighted_indices = [i for i, p in enumerate(plugins) if p.highlighted]
        non_highlighted_indices = [
            i for i, p in enumerate(plugins) if not p.highlighted
        ]
        if highlighted_indices and non_highlighted_indices:
            assert max(highlighted_indices) < min(non_highlighted_indices)
