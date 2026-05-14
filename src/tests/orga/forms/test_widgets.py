# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from types import SimpleNamespace

import pytest
from django.conf import settings

from pretalx.orga.forms.widgets import (
    FontSelect,
    HeaderSelect,
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


def test_font_select_init_stores_fonts_and_default():
    fonts = {"TestFont": {"regular": {"woff2": "fonts/test.woff2"}}}
    widget = FontSelect(fonts=fonts, default_font="Fallback")

    assert widget.fonts == fonts
    assert widget.default_font == "Fallback"


def test_font_select_init_defaults_to_empty():
    widget = FontSelect()

    assert widget.fonts == {}
    assert widget.default_font is None


def test_font_select_create_option_sets_font_family_for_known_font():
    fonts = {"TestFont": {"regular": {"woff2": "fonts/test.woff2"}}}
    widget = FontSelect(
        fonts=fonts, choices=[("", "Default"), ("TestFont", "TestFont")]
    )

    option = widget.create_option("field", "TestFont", "TestFont", False, 1)

    assert option["attrs"]["data-font-family"] == "TestFont"


def test_font_select_create_option_sets_sample_data():
    fonts = {
        "TestFont": {
            "regular": {"woff2": "fonts/test.woff2"},
            "sample": "مرحبا بالعالم",
        }
    }
    widget = FontSelect(fonts=fonts, choices=[("TestFont", "TestFont")])

    option = widget.create_option("field", "TestFont", "TestFont", False, 0)

    assert option["attrs"]["data-font-family"] == "TestFont"
    assert option["attrs"]["data-font-sample"] == "مرحبا بالعالم"


def test_font_select_create_option_empty_value_uses_default_font():
    fonts = {"TestFont": {"regular": {"woff2": "fonts/test.woff2"}}}
    widget = FontSelect(
        fonts=fonts,
        choices=[("", "Default"), ("TestFont", "TestFont")],
        default_font="Titillium Web",
    )

    option = widget.create_option("field", "", "Default", False, 0)

    assert option["attrs"]["data-font-family"] == "Titillium Web"


def test_font_select_create_option_empty_value_without_default():
    fonts = {"TestFont": {"regular": {"woff2": "fonts/test.woff2"}}}
    widget = FontSelect(fonts=fonts, choices=[("", "Default")])

    option = widget.create_option("field", "", "Default", False, 0)

    assert "data-font-family" not in option["attrs"]
