import pytest
from django.test import override_settings

from pretalx.common.plugins import (
    get_all_plugins,
    get_all_plugins_grouped,
    plugin_group_key,
    plugin_sort_key,
)
from tests.dummy_app import PluginApp

pytestmark = pytest.mark.unit


def test_get_all_plugins_includes_dummy_plugin():
    plugins = get_all_plugins()

    assert PluginApp.PretalxPluginMeta in plugins


def test_get_all_plugins_sets_plugin_metadata():
    plugins = get_all_plugins()

    dummy = next(p for p in plugins if p == PluginApp.PretalxPluginMeta)
    assert dummy.module == "tests.dummy_app"
    assert dummy.app.name == "tests.dummy_app"
    assert dummy.highlighted is False


def test_get_all_plugins_sets_highlighted_true_when_in_settings():
    with override_settings(HIGHLIGHTED_PLUGINS=["tests.dummy_app"]):
        plugins = get_all_plugins()

    dummy = next(p for p in plugins if p == PluginApp.PretalxPluginMeta)
    assert dummy.highlighted is True


@pytest.mark.parametrize("available", (True, False))
def test_get_all_plugins_filters_by_event_availability(available):
    """Plugins are included or excluded based on is_available() for the event."""

    class FakeEvent:
        _dummy_available = available

    plugins = get_all_plugins(event=FakeEvent())

    assert (PluginApp.PretalxPluginMeta in plugins) is available


def test_get_all_plugins_sorted_highlighted_first():
    with override_settings(HIGHLIGHTED_PLUGINS=["tests.dummy_app"]):
        plugins = get_all_plugins()

    assert plugins[0].highlighted is True


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
    """Sorting ignores 'pretalx ' prefix so 'pretalx Foo' sorts as 'foo'."""
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


def test_get_all_plugins_grouped_returns_dict_with_tuple_keys():
    result = get_all_plugins_grouped()

    for key in result:
        assert isinstance(key, tuple)
        assert len(key) == 2
        category_code, _label = key
        assert isinstance(category_code, str)


def test_get_all_plugins_grouped_includes_dummy_plugin():
    result = get_all_plugins_grouped()

    all_plugins = [p for plugins in result.values() for p in plugins]
    assert PluginApp.PretalxPluginMeta in all_plugins


def test_get_all_plugins_grouped_filters_hidden_plugins():
    """Plugins whose name starts with '.' are filtered out by default."""
    result = get_all_plugins_grouped(filter_visible=True)
    all_plugins = [p for plugins in result.values() for p in plugins]
    for plugin in all_plugins:
        assert not plugin.name.startswith(".")


def test_get_all_plugins_grouped_no_filter():
    """With filter_visible=False, all plugins are included."""
    result_filtered = get_all_plugins_grouped(filter_visible=True)
    result_unfiltered = get_all_plugins_grouped(filter_visible=False)

    filtered_count = sum(len(v) for v in result_filtered.values())
    unfiltered_count = sum(len(v) for v in result_unfiltered.values())
    assert unfiltered_count >= filtered_count


def test_get_all_plugins_grouped_highlighted_sorted_first_within_category():
    with override_settings(HIGHLIGHTED_PLUGINS=["tests.dummy_app"]):
        result = get_all_plugins_grouped()

    other_plugins = next(
        plugins for (code, _), plugins in result.items() if code == "OTHER"
    )
    assert other_plugins[0].highlighted is True
