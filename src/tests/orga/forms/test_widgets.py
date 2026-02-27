from types import SimpleNamespace

import pytest
from django.conf import settings

from pretalx.orga.forms.widgets import (
    HeaderSelect,
    IconSelect,
    MultipleLanguagesWidget,
    PluginSelectWidget,
)

pytestmark = pytest.mark.unit


def test_plugin_select_widget_stores_plugins_dict():
    plugin_a = SimpleNamespace(module="plugin_a", name="Plugin A")
    plugin_b = SimpleNamespace(module="plugin_b", name="Plugin B")
    widget = PluginSelectWidget(plugins=[plugin_a, plugin_b])

    assert widget.plugins == {"plugin_a": plugin_a, "plugin_b": plugin_b}


def test_plugin_select_widget_empty_plugins():
    widget = PluginSelectWidget()

    assert widget.plugins == {}


def test_plugin_select_widget_create_option_adds_plugin():
    plugin = SimpleNamespace(module="my_plugin", name="My Plugin")
    widget = PluginSelectWidget(plugins=[plugin])

    opt = widget.create_option("plugins", "my_plugin", "My Plugin", False, 0)

    assert opt["plugin"] is plugin


def test_plugin_select_widget_create_option_missing_plugin():
    widget = PluginSelectWidget(plugins=[])

    opt = widget.create_option("plugins", "unknown", "Unknown", False, 0)

    assert opt["plugin"] is None


def test_plugin_select_widget_templates():
    widget = PluginSelectWidget()

    assert widget.template_name == "orga/widgets/plugin_select.html"
    assert widget.option_template_name == "orga/widgets/plugin_option.html"


def test_plugin_select_widget_media():
    widget = PluginSelectWidget()

    assert widget.media._css["all"] == ["orga/css/ui/plugins.css"]


def test_header_select_template():
    widget = HeaderSelect()

    assert widget.option_template_name == "orga/widgets/header_option.html"


def test_header_select_media():
    widget = HeaderSelect()

    assert widget.media._css["all"] == [
        "common/css/headers/pcb.css",
        "common/css/headers/bubbles.css",
        "common/css/headers/signal.css",
        "common/css/headers/topo.css",
        "common/css/headers/graph.css",
        "orga/css/forms/header.css",
    ]


def test_icon_select_template():
    widget = IconSelect()

    assert widget.option_template_name == "orga/widgets/icon_option.html"


def test_icon_select_media():
    widget = IconSelect()

    assert widget.media._css["all"] == ["orga/css/forms/icon.css"]


def test_multiple_languages_widget_init_adds_css_class():
    widget = MultipleLanguagesWidget()

    assert "form-check form-check-languages" in widget.attrs["class"]


def test_multiple_languages_widget_init_preserves_existing_class():
    widget = MultipleLanguagesWidget(attrs={"class": "custom"})

    assert "custom" in widget.attrs["class"]
    assert "form-check-languages" in widget.attrs["class"]


def test_multiple_languages_widget_sort_groups_by_official_status():
    widget = MultipleLanguagesWidget()
    widget.choices = [("en", "English"), ("de", "German"), ("ar", "Arabic")]

    widget.sort()

    official_group, community_group = widget.choices
    official_values = [c[0] for c in official_group[1]]
    community_values = [c[0] for c in community_group[1]]
    assert official_values == ["en", "de"]
    assert community_values == ["ar"]


def test_multiple_languages_widget_optgroups_sorts_official_first():
    """optgroups sorts choices so official languages precede community ones."""
    widget = MultipleLanguagesWidget()
    widget.choices = [("ar", "Arabic"), ("en", "English")]

    groups = widget.optgroups("lang", [], attrs={})

    values = [opt["value"] for _, opts, _ in groups for opt in opts]
    assert values.index("en") < values.index("ar")


def test_multiple_languages_widget_options_sorts_official_first():
    """options sorts choices so official languages precede community ones."""
    widget = MultipleLanguagesWidget()
    widget.choices = [("ar", "Arabic"), ("en", "English")]

    result = widget.options("lang", [], attrs={})

    assert result is not None
    # Verify that sort was applied: choices are now grouped
    official_group, community_group = widget.choices
    assert [c[0] for c in official_group[1]] == ["en"]
    assert [c[0] for c in community_group[1]] == ["ar"]


def test_multiple_languages_widget_create_option_adds_language_data():
    widget = MultipleLanguagesWidget()

    opt = widget.create_option("lang", "en", "English", False, 0, attrs={})

    assert opt["attrs"]["lang"] == "en"
    assert opt["official"] is True
    assert opt["percentage"] == settings.LANGUAGES_INFORMATION["en"]["percentage"]


def test_multiple_languages_widget_create_option_unofficial_language():
    widget = MultipleLanguagesWidget()

    opt = widget.create_option("lang", "ar", "Arabic", False, 0, attrs={})

    assert opt["attrs"]["lang"] == "ar"
    assert opt["official"] is False
    assert opt["percentage"] == settings.LANGUAGES_INFORMATION["ar"]["percentage"]
