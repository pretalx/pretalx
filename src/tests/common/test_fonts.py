# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.common.fonts import get_font_css, get_font_definitions, get_fonts
from pretalx.common.signals import register_fonts
from tests.factories import EventFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

SAMPLE_FONTS = {
    "TestFont": {
        "regular": {
            "truetype": "fonts/test-regular.ttf",
            "woff2": "fonts/test-regular.woff2",
        },
        "bold": {"truetype": "fonts/test-bold.ttf", "woff2": "fonts/test-bold.woff2"},
    }
}


def test_get_fonts_returns_empty_when_no_plugins(register_signal_handler):
    event = EventFactory()

    result = get_fonts(event)

    assert result == {}


def test_get_fonts_returns_plugin_fonts(register_signal_handler):
    event = EventFactory()

    def handler(signal, sender, **kwargs):
        return SAMPLE_FONTS

    register_signal_handler(register_fonts, handler)
    result = get_fonts(event)

    assert set(result.keys()) == {"TestFont"}
    assert result["TestFont"]["regular"]["truetype"] == "fonts/test-regular.ttf"


def test_get_fonts_merges_multiple_plugins(register_signal_handler):
    event = EventFactory()

    def handler_a(signal, sender, **kwargs):
        return {"FontA": {"regular": {"truetype": "a.ttf", "woff2": "a.woff2"}}}

    def handler_b(signal, sender, **kwargs):
        return {"FontB": {"regular": {"truetype": "b.ttf", "woff2": "b.woff2"}}}

    register_signal_handler(register_fonts, handler_a)
    register_signal_handler(register_fonts, handler_b)
    result = get_fonts(event)

    assert set(result.keys()) == {"FontA", "FontB"}


def test_get_fonts_with_none_event():
    """get_fonts(None) returns empty — no signal sent without an event."""
    result = get_fonts(None)

    assert result == {}


def test_get_font_css_returns_empty_when_no_custom_fonts():
    event = EventFactory()

    result = get_font_css(event)

    assert result == ""


def test_get_font_css_generates_font_face_and_variables(register_signal_handler):
    event = EventFactory(
        display_settings={
            "schedule": "grid",
            "imprint_url": None,
            "header_pattern": "",
            "html_export_url": "",
            "meta_noindex": False,
            "heading_font": "TestFont",
            "text_font": "",
            "texts": {"agenda_session_above": "", "agenda_session_below": ""},
        }
    )

    def handler(signal, sender, **kwargs):
        return SAMPLE_FONTS

    register_signal_handler(register_fonts, handler)
    result = get_font_css(event)

    assert result.count("@font-face {") == 2
    assert result.count('font-family: "TestFont"') == 2
    root_block = result.split(":root {\n")[1].split("\n}")[0].strip()
    assert root_block == '--font-family-title: "TestFont", var(--font-fallback);'


def test_get_font_css_both_fonts(register_signal_handler):
    event = EventFactory(
        display_settings={
            "schedule": "grid",
            "imprint_url": None,
            "header_pattern": "",
            "html_export_url": "",
            "meta_noindex": False,
            "heading_font": "TestFont",
            "text_font": "TestFont",
            "texts": {"agenda_session_above": "", "agenda_session_below": ""},
        }
    )

    def handler(signal, sender, **kwargs):
        return SAMPLE_FONTS

    register_signal_handler(register_fonts, handler)
    result = get_font_css(event)

    assert result.count("@font-face {") == 2
    root_block = result.split(":root {\n")[1].split("\n}")[0]
    root_lines = [line.strip() for line in root_block.strip().splitlines()]
    assert root_lines == [
        '--font-family-title: "TestFont", var(--font-fallback);',
        '--font-family: "TestFont", var(--font-fallback);',
    ]


def test_get_font_css_ignores_unknown_font(register_signal_handler):
    """If event references a font that no plugin provides, skip it."""
    event = EventFactory(
        display_settings={
            "schedule": "grid",
            "imprint_url": None,
            "header_pattern": "",
            "html_export_url": "",
            "meta_noindex": False,
            "heading_font": "NonexistentFont",
            "text_font": "",
            "texts": {"agenda_session_above": "", "agenda_session_below": ""},
        }
    )

    result = get_font_css(event)

    assert result == ""


def test_get_fonts_ignores_non_dict_responses(register_signal_handler):
    """Receivers returning non-dict values (e.g. exceptions) are skipped."""
    event = EventFactory()

    def bad_handler(signal, sender, **kwargs):
        return "not a dict"

    def good_handler(signal, sender, **kwargs):
        return {"GoodFont": {"regular": {"woff2": "fonts/good.woff2"}}}

    register_signal_handler(register_fonts, bad_handler)
    register_signal_handler(register_fonts, good_handler)
    result = get_fonts(event)

    assert set(result.keys()) == {"GoodFont"}


def test_get_font_css_text_font_only(register_signal_handler):
    """Setting only text_font (no heading_font) generates correct CSS."""
    event = EventFactory(
        display_settings={
            "schedule": "grid",
            "imprint_url": None,
            "header_pattern": "",
            "html_export_url": "",
            "meta_noindex": False,
            "heading_font": "",
            "text_font": "TestFont",
            "texts": {"agenda_session_above": "", "agenda_session_below": ""},
        }
    )

    def handler(signal, sender, **kwargs):
        return SAMPLE_FONTS

    register_signal_handler(register_fonts, handler)
    result = get_font_css(event)

    assert "@font-face {" in result
    root_block = result.split(":root {\n")[1].split("\n}")[0].strip()
    assert root_block == '--font-family: "TestFont", var(--font-fallback);'
    assert "--font-family-title" not in result


def test_get_font_css_returns_empty_when_selected_font_not_in_available(
    register_signal_handler,
):
    """Event references a font name that doesn't match any plugin-provided font."""
    event = EventFactory(
        display_settings={
            "schedule": "grid",
            "imprint_url": None,
            "header_pattern": "",
            "html_export_url": "",
            "meta_noindex": False,
            "heading_font": "WrongName",
            "text_font": "",
            "texts": {"agenda_session_above": "", "agenda_session_below": ""},
        }
    )

    def handler(signal, sender, **kwargs):
        return {"ActualFont": {"regular": {"woff2": "fonts/actual.woff2"}}}

    register_signal_handler(register_fonts, handler)
    result = get_font_css(event)

    assert result == ""


def test_get_font_css_with_font_having_no_recognized_formats(register_signal_handler):
    """Font is selected but has no woff2/woff/truetype — produces variable-only CSS."""
    event = EventFactory(
        display_settings={
            "schedule": "grid",
            "imprint_url": None,
            "header_pattern": "",
            "html_export_url": "",
            "meta_noindex": False,
            "heading_font": "NoFormatFont",
            "text_font": "",
            "texts": {"agenda_session_above": "", "agenda_session_below": ""},
        }
    )

    def handler(signal, sender, **kwargs):
        return {"NoFormatFont": {"regular": {"svg": "fonts/no-format.svg"}}}

    register_signal_handler(register_fonts, handler)
    result = get_font_css(event)

    assert "@font-face" not in result
    assert "--font-family-title" in result


def test_get_font_definitions_skips_unknown_font_names():
    fonts = {"KnownFont": {"regular": {"woff2": "fonts/known.woff2"}}}

    result = get_font_definitions(fonts, ["UnknownFont"])

    assert result == ""


def test_get_font_definitions_skips_non_dict_variant_values():
    """Non-dict values like 'sample' strings in font data are skipped."""
    fonts = {
        "MyFont": {"regular": {"woff2": "fonts/my.woff2"}, "sample": "Some sample text"}
    }

    result = get_font_definitions(fonts, ["MyFont"])

    assert result.count("@font-face {") == 1
    assert "sample" not in result.lower().split("@font-face")[0]


def test_get_font_definitions_skips_variant_with_no_recognized_formats():
    """A variant dict with no woff2/woff/truetype keys produces no @font-face rule."""
    fonts = {"MyFont": {"regular": {"svg": "fonts/my.svg"}}}

    result = get_font_definitions(fonts, ["MyFont"])

    assert result == ""


def test_get_font_definitions_italic_and_bolditalic_styles():
    """Italic variants get font-style: italic, bolditalic gets both bold weight and italic style."""
    fonts = {
        "MyFont": {
            "italic": {"woff2": "fonts/my-italic.woff2"},
            "bolditalic": {"woff2": "fonts/my-bolditalic.woff2"},
        }
    }

    result = get_font_definitions(fonts, ["MyFont"])

    blocks = result.split("@font-face {")[1:]
    assert len(blocks) == 2
    for block in blocks:
        assert "font-style: italic;" in block
    assert "font-weight: bold;" in blocks[1]
    assert "font-weight: normal;" in blocks[0]
