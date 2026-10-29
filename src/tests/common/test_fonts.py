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


def test_get_fonts_merges_dict_responses_of_all_plugins(register_signal_handler):
    event = EventFactory()
    assert get_fonts(None) == {}
    assert get_fonts(event) == {}

    def handler_a(signal, sender, **kwargs):
        return SAMPLE_FONTS

    def handler_b(signal, sender, **kwargs):
        return {"FontB": {"regular": {"truetype": "b.ttf", "woff2": "b.woff2"}}}

    def bad_handler(signal, sender, **kwargs):
        return "not a dict"

    register_signal_handler(register_fonts, handler_a)
    register_signal_handler(register_fonts, handler_b)
    register_signal_handler(register_fonts, bad_handler)

    assert get_fonts(event) == {
        **SAMPLE_FONTS,
        "FontB": {"regular": {"truetype": "b.ttf", "woff2": "b.woff2"}},
    }


def _font_event(heading_font, text_font):
    return EventFactory(
        display_settings={
            "schedule": "grid",
            "imprint_url": None,
            "header_pattern": "",
            "html_export_url": "",
            "meta_noindex": False,
            "heading_font": heading_font,
            "text_font": text_font,
            "texts": {"agenda_session_above": "", "agenda_session_below": ""},
        }
    )


def _root_lines(css):
    blocks = css.split(":root {\n")
    if len(blocks) < 2:
        return []
    return [line.strip() for line in blocks[1].split("\n}")[0].strip().splitlines()]


TITLE = '--font-family-title: "TestFont", var(--font-fallback);'
TEXT = '--font-family: "TestFont", var(--font-fallback);'


@pytest.mark.parametrize(
    ("heading_font", "text_font", "fonts", "font_faces", "root_lines"),
    (
        ("", "", SAMPLE_FONTS, 0, []),
        ("TestFont", "", SAMPLE_FONTS, 2, [TITLE]),
        ("", "TestFont", SAMPLE_FONTS, 2, [TEXT]),
        ("TestFont", "TestFont", SAMPLE_FONTS, 2, [TITLE, TEXT]),
        ("NonexistentFont", "", {}, 0, []),
        (
            "WrongName",
            "",
            {"ActualFont": {"regular": {"woff2": "fonts/a.woff2"}}},
            0,
            [],
        ),
        (
            "TestFont",
            "",
            {"TestFont": {"regular": {"svg": "fonts/no-format.svg"}}},
            0,
            [TITLE],
        ),
    ),
    ids=(
        "no_custom_fonts",
        "heading_font",
        "text_font",
        "both_fonts",
        "unknown_font_without_plugins",
        "selected_font_not_offered",
        "font_without_recognised_formats",
    ),
)
def test_get_font_css(
    register_signal_handler, heading_font, text_font, fonts, font_faces, root_lines
):
    event = _font_event(heading_font, text_font)

    def handler(signal, sender, **kwargs):
        return fonts

    register_signal_handler(register_fonts, handler)

    result = get_font_css(event)

    assert result.count("@font-face {") == font_faces
    assert result.count('font-family: "TestFont";') == font_faces
    assert _root_lines(result) == root_lines
    assert (result == "") is (not root_lines)


@pytest.mark.parametrize(
    ("fonts", "names"),
    (
        ({"KnownFont": {"regular": {"woff2": "fonts/known.woff2"}}}, ["UnknownFont"]),
        ({"MyFont": {"regular": {"svg": "fonts/my.svg"}}}, ["MyFont"]),
    ),
    ids=("unknown_font_name", "no_recognised_formats"),
)
def test_get_font_definitions_skips_unusable_fonts(fonts, names):
    assert get_font_definitions(fonts, names) == ""


def test_get_font_definitions_skips_non_dict_variant_values():
    fonts = {
        "MyFont": {"regular": {"woff2": "fonts/my.woff2"}, "sample": "Some sample text"}
    }

    result = get_font_definitions(fonts, ["MyFont"])

    assert result.count("@font-face {") == 1
    assert "sample" not in result.lower().split("@font-face")[0]


def test_get_font_definitions_italic_and_bolditalic_styles():
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
