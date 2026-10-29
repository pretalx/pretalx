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

COMMUNITY_LABEL = (
    f"{MultipleLanguagesWidget.community_group_label}"
    f"\n{MultipleLanguagesWidget.community_note}"
)


def test_plugin_select_widget_create_option_adds_plugin():
    plugin = SimpleNamespace(module="my_plugin", name="My Plugin")
    widget = PluginSelectWidget(plugins=[plugin])

    known = widget.create_option("plugins", "my_plugin", "My Plugin", False, 0)
    unknown = widget.create_option("plugins", "unknown", "Unknown", False, 1)

    assert known["plugin"] is plugin
    assert unknown["plugin"] is None


def test_language_widget_optgroups_splits_official_and_community():
    widget = MultipleLanguagesWidget()
    widget.choices = [("ar", "Arabic"), ("en", "English"), ("de", "German")]

    groups = widget.optgroups("locale", ["ar"], attrs={})

    assert [group[0] for group in groups] == [
        str(MultipleLanguagesWidget.official_group_label),
        COMMUNITY_LABEL,
    ]
    assert str(MultipleLanguagesWidget.community_note).endswith(
        "translate.pretalx.com."
    )
    assert [(option["value"], option["selected"]) for option in groups[0][1]] == [
        ("en", False),
        ("de", False),
    ]
    assert [(option["value"], option["selected"]) for option in groups[1][1]] == [
        ("ar", True)
    ]
    assert [group[2] for group in groups] == [0, 1]


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


@pytest.mark.parametrize(
    ("widget_class", "expects_multiple"),
    ((MultipleLanguagesWidget, True), (LanguageWidget, False)),
    ids=("multiple", "single"),
)
def test_language_widget_renders_note_in_community_group_label(
    widget_class, expects_multiple
):
    widget = widget_class()
    widget.choices = [("en", "English"), ("ar", "Arabic")]

    rendered = widget.render("locale", ["ar"], {"id": "id_locale"})

    assert ("multiple" in rendered) is expects_multiple
    assert 'data-search-fields="label,customProperties"' in rendered
    assert 'class="enhanced language-select"' in rendered
    assert f'<optgroup label="{COMMUNITY_LABEL}">' in rendered
    assert '<option value="en" lang="en" data-custom-properties="English">' in rendered
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
    ("fonts", "default_font", "value", "family", "sample"),
    (
        ({"TestFont": {"regular": {}}}, None, "TestFont", "TestFont", None),
        (
            {"TestFont": {"regular": {}, "sample": "مرحبا بالعالم"}},
            None,
            "TestFont",
            "TestFont",
            "مرحبا بالعالم",
        ),
        ({"TestFont": {"regular": {}}}, "Titillium Web", "", "Titillium Web", None),
        ({"TestFont": {"regular": {}}}, None, "", None, None),
    ),
    ids=("known-font", "font-with-sample", "empty-with-default", "empty-no-default"),
)
def test_font_select_create_option(fonts, default_font, value, family, sample):
    widget = FontSelect(
        fonts=fonts,
        choices=[("", "Default"), ("TestFont", "TestFont")],
        default_font=default_font,
    )

    option = widget.create_option("field", value, value or "Default", False, 0)

    assert option["attrs"].get("data-font-family") == family
    assert option["attrs"].get("data-font-sample") == sample
