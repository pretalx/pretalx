# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.test import override_settings

from pretalx.orga.forms.widgets import (
    FontSelect,
    LanguageWidget,
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


def test_language_widget_optgroups_splits_official_and_community():
    widget = MultipleLanguagesWidget()
    widget.choices = [("ar", "Arabic"), ("en", "English"), ("de", "German")]

    groups = widget.optgroups("locale", [], attrs={})

    community_label = (
        f"{MultipleLanguagesWidget.community_group_label}"
        f"\n{MultipleLanguagesWidget.community_note}"
    )
    assert [group[0] for group in groups] == [
        str(MultipleLanguagesWidget.official_group_label),
        community_label,
    ]
    assert str(MultipleLanguagesWidget.community_note).endswith(
        "translate.pretalx.com."
    )
    assert [option["value"] for option in groups[0][1]] == ["en", "de"]
    assert [option["value"] for option in groups[1][1]] == ["ar"]
    assert [group[2] for group in groups] == [0, 1]


def test_language_widget_optgroups_marks_selected():
    widget = MultipleLanguagesWidget()
    widget.choices = [("en", "English"), ("ar", "Arabic")]

    groups = widget.optgroups("locale", ["ar"], attrs={})

    assert groups[0][1][0]["selected"] is False
    assert groups[1][1][0]["selected"] is True


@pytest.mark.parametrize(
    ("language", "natural_name", "expected_description"),
    (
        ("en", "English", None),
        (
            "ar",
            "اَلْعَرَبِيَّةُ",
            f"{settings.LANGUAGES_INFORMATION['ar']['percentage']} % translated",
        ),
        (
            "es",
            "Español",
            f"{settings.LANGUAGES_INFORMATION['es']['percentage']} % translated",
        ),
    ),
    ids=("official", "community_arabic", "community_spanish"),
)
def test_language_widget_option_attributes(
    language, natural_name, expected_description
):
    widget = MultipleLanguagesWidget()

    option = widget.create_option("locale", language, "Label", False, 0, attrs={})

    assert option["attrs"]["lang"] == language
    assert option["attrs"]["data-custom-properties"] == natural_name
    assert option["attrs"].get("data-description") == expected_description


def test_language_widget_community_option_without_percentage():
    # Plugin-provided languages have no translation percentage.
    languages = dict(settings.LANGUAGES_INFORMATION)
    languages["xx"] = {
        "name": "Plugin language",
        "natural_name": "Plugin language",
        "official": False,
        "percentage": None,
    }
    widget = MultipleLanguagesWidget()

    with override_settings(LANGUAGES_INFORMATION=languages):
        option = widget.create_option("locale", "xx", "Plugin language", False, 0)

    assert "data-description" not in option["attrs"]


def test_language_widget_context_opts_into_natural_name_search():
    widget = MultipleLanguagesWidget()
    widget.choices = [("en", "English"), ("ar", "Arabic")]

    context = widget.get_context("locale", [], {"id": "id_locale"})

    attrs = context["widget"]["attrs"]
    assert attrs["data-search-fields"] == "label,customProperties"
    assert "language-select" in attrs["class"]
    assert "enhanced" in attrs["class"]


def test_language_widget_renders_note_in_community_group_label():
    widget = MultipleLanguagesWidget()
    widget.choices = [("en", "English"), ("ar", "Arabic")]

    rendered = widget.render("locale", ["ar"], {"id": "id_locale"})

    expected_label = (
        f"{MultipleLanguagesWidget.community_group_label}"
        f"\n{MultipleLanguagesWidget.community_note}"
    )
    assert f'<optgroup label="{expected_label}">' in rendered
    assert (
        '<option value="ar" selected lang="ar" data-custom-properties="اَلْعَرَبِيَّةُ" data-description='
        in rendered
    )
    # The note lives in an attribute, so it cannot carry a link, and it needs
    # no separate element to point at.
    assert "<a " not in rendered
    assert "aria-describedby" not in rendered


def test_language_widget_renders_no_note_without_community_languages():
    widget = MultipleLanguagesWidget()
    widget.choices = [("en", "English"), ("de", "German")]

    rendered = widget.render("locale", ["en"], {"id": "id_locale"})

    assert str(MultipleLanguagesWidget.community_group_label) not in rendered
    assert "translate.pretalx.com" not in rendered


@pytest.mark.parametrize(
    ("widget_class", "expects_multiple"),
    ((MultipleLanguagesWidget, True), (LanguageWidget, False)),
    ids=("multiple", "single"),
)
def test_language_widget_renders_matching_select_type(widget_class, expects_multiple):
    widget = widget_class()
    widget.choices = [("en", "English"), ("ar", "Arabic")]

    rendered = widget.render("locale", ["en"], {"id": "id_locale"})

    assert ("multiple" in rendered) is expects_multiple
    assert '<option value="en" selected lang="en"' in rendered


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
