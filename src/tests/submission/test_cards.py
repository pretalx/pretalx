# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from unittest.mock import Mock

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

from pretalx.common.signals import register_fonts
from pretalx.event.models.event import default_display_settings
from pretalx.submission.cards import (
    SubmissionCard,
    _register_plugin_font,
    _resolve_fonts,
    _text,
    build_cards,
    get_story,
    get_style,
)
from tests.factories import EventFactory, SpeakerFactory, SubmissionFactory

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("input_text", "max_length", "expected"),
    (
        (None, None, ""),
        ("", None, ""),
        ("hello", None, "hello"),
        ("12345", 3, "12…"),
        ("12345", 5, "12345"),
        ("a-b", None, "a-&hairsp;b"),
        ("a<b", None, "a&lt;b"),
    ),
)
def test_text_normalizes_escapes_and_truncates(input_text, max_length, expected):
    assert _text(input_text, max_length) == expected


def test_text_normalizes_combining_characters_to_nfc():
    """ReportLab cannot render combination characters, so _text normalises to NFC."""
    assert _text("e\u0301") == "é"


@pytest.mark.parametrize(
    ("duration", "expected_height"),
    (
        (10, 2.5 * 30 * mm),  # short durations clamped to 30 min
        (60, 2.5 * 60 * mm),  # actual duration used
        (9999, A4[1]),  # capped at A4 page height
    ),
)
def test_submission_card_init_height(duration, expected_height):
    sub = Mock(get_duration=Mock(return_value=duration))
    card = SubmissionCard(
        sub,
        get_style("Titillium-Bold", "Muli", "Muli-Italic"),
        100 * mm,
        "Titillium-Bold",
    )
    assert card.height == expected_height


def test_submission_card_coord_transforms_to_bottom_up():
    sub = Mock(get_duration=Mock(return_value=30))
    card = SubmissionCard(
        sub,
        get_style("Titillium-Bold", "Muli", "Muli-Italic"),
        100 * mm,
        "Titillium-Bold",
    )
    x, y = card.coord(10, 20, unit=mm)
    assert x == 10 * mm
    assert y == card.height - 20 * mm


@pytest.mark.django_db
def test_get_story_creates_card_per_submission():
    subs = [Mock(get_duration=Mock(return_value=30)) for _ in range(3)]
    doc = Mock(width=A4[0])
    event = EventFactory()

    story = get_story(doc, subs, event)

    assert len(story) == 3
    assert all(isinstance(c, SubmissionCard) for c in story)
    assert all(c.width == doc.width / 2 for c in story)


@pytest.mark.parametrize(
    ("abstract", "notes"), (("An abstract", "Some notes"), ("", ""))
)
@pytest.mark.django_db
def test_build_cards_returns_pdf(abstract, notes):
    """Exercises SubmissionCard.draw with and without abstract/notes branches."""
    event = EventFactory()
    submission = SubmissionFactory(event=event, abstract=abstract, notes=notes)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)

    response = build_cards([submission], event)

    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].startswith("attachment;")
    assert event.slug in response["Content-Disposition"]
    assert len(response.content) > 0


def test_register_plugin_font_registers_regular_variant():
    font_data = {"regular": {"truetype": "fonts/mulish-v12-latin-ext-regular.ttf"}}

    registered = _register_plugin_font("TestPluginFont", font_data)

    assert registered == {"regular"}


def test_register_plugin_font_registers_multiple_variants():
    font_data = {
        "regular": {"truetype": "fonts/mulish-v12-latin-ext-regular.ttf"},
        "italic": {"truetype": "fonts/mulish-v12-latin-ext-italic.ttf"},
        "bold": {"truetype": "fonts/titillium-web-v17-latin-ext-600.ttf"},
    }

    registered = _register_plugin_font("TestMultiFont", font_data)

    assert registered == {"regular", "italic", "bold"}


def test_register_plugin_font_skips_missing_truetype():
    """Variants without a truetype path are skipped."""
    font_data = {"regular": {"woff2": "fonts/mulish-v12-latin-ext-regular.woff2"}}

    registered = _register_plugin_font("TestNoTTF", font_data)

    assert registered == set()


def test_register_plugin_font_skips_unresolvable_path():
    """Variants with a truetype path that finders.find() can't resolve are skipped."""
    font_data = {"regular": {"truetype": "fonts/nonexistent-font.ttf"}}

    registered = _register_plugin_font("TestBadPath", font_data)

    assert registered == set()


def test_register_plugin_font_skips_non_dict_variant():
    """Non-dict values in font data (like 'sample' strings) are skipped."""
    font_data = {
        "regular": {"truetype": "fonts/mulish-v12-latin-ext-regular.ttf"},
        "sample": "Example text",
    }

    registered = _register_plugin_font("TestSampleFont", font_data)

    assert registered == {"regular"}


def test_resolve_fonts_returns_defaults_without_event():
    heading, text, text_italic = _resolve_fonts(None)

    assert heading == "Titillium-Bold"
    assert text == "Muli"
    assert text_italic == "Muli-Italic"


@pytest.mark.django_db
def test_resolve_fonts_returns_defaults_when_no_custom_fonts_set():
    event = EventFactory()

    heading, text, text_italic = _resolve_fonts(event)

    assert heading == "Titillium-Bold"
    assert text == "Muli"
    assert text_italic == "Muli-Italic"


@pytest.mark.django_db
def test_resolve_fonts_uses_custom_heading_font_with_bold(register_signal_handler):
    """When a plugin font with bold variant is set as heading font, the Bold variant is used."""
    settings = default_display_settings()
    settings["heading_font"] = "CustomHeading"
    event = EventFactory(display_settings=settings)

    def handler(signal, sender, **kwargs):
        return {
            "CustomHeading": {
                "regular": {"truetype": "fonts/mulish-v12-latin-ext-regular.ttf"},
                "bold": {"truetype": "fonts/titillium-web-v17-latin-ext-600.ttf"},
            }
        }

    register_signal_handler(register_fonts, handler)
    heading, text, text_italic = _resolve_fonts(event)

    assert heading == "CustomHeading-Bold"
    assert text == "Muli"
    assert text_italic == "Muli-Italic"


@pytest.mark.django_db
def test_resolve_fonts_uses_custom_heading_font_without_bold(register_signal_handler):
    """When a plugin font has no bold variant, the regular name is used for headings."""
    settings = default_display_settings()
    settings["heading_font"] = "CustomHeading"
    event = EventFactory(display_settings=settings)

    def handler(signal, sender, **kwargs):
        return {
            "CustomHeading": {
                "regular": {"truetype": "fonts/mulish-v12-latin-ext-regular.ttf"}
            }
        }

    register_signal_handler(register_fonts, handler)
    heading, _text, _text_italic = _resolve_fonts(event)

    assert heading == "CustomHeading"


@pytest.mark.django_db
def test_resolve_fonts_uses_custom_text_font_with_italic(register_signal_handler):
    settings = default_display_settings()
    settings["text_font"] = "CustomText"
    event = EventFactory(display_settings=settings)

    def handler(signal, sender, **kwargs):
        return {
            "CustomText": {
                "regular": {"truetype": "fonts/mulish-v12-latin-ext-regular.ttf"},
                "italic": {"truetype": "fonts/mulish-v12-latin-ext-italic.ttf"},
            }
        }

    register_signal_handler(register_fonts, handler)
    _heading, text, text_italic = _resolve_fonts(event)

    assert text == "CustomText"
    assert text_italic == "CustomText-Italic"


@pytest.mark.django_db
def test_resolve_fonts_uses_custom_text_font_without_italic(register_signal_handler):
    """When a text font has no italic variant, the regular name is used for both."""
    settings = default_display_settings()
    settings["text_font"] = "CustomText"
    event = EventFactory(display_settings=settings)

    def handler(signal, sender, **kwargs):
        return {
            "CustomText": {
                "regular": {"truetype": "fonts/mulish-v12-latin-ext-regular.ttf"}
            }
        }

    register_signal_handler(register_fonts, handler)
    _heading, text, text_italic = _resolve_fonts(event)

    assert text == "CustomText"
    assert text_italic == "CustomText"


@pytest.mark.django_db
def test_resolve_fonts_heading_falls_back_when_no_regular_truetype(
    register_signal_handler,
):
    """When the heading font has no resolvable regular truetype, defaults are kept."""
    settings = default_display_settings()
    settings["heading_font"] = "NoTTF"
    event = EventFactory(display_settings=settings)

    def handler(signal, sender, **kwargs):
        return {
            "NoTTF": {"regular": {"woff2": "fonts/mulish-v12-latin-ext-regular.woff2"}}
        }

    register_signal_handler(register_fonts, handler)
    heading, _text, _text_italic = _resolve_fonts(event)

    assert heading == "Titillium-Bold"


@pytest.mark.django_db
def test_resolve_fonts_text_falls_back_when_no_regular_truetype(
    register_signal_handler,
):
    """When the text font has no resolvable regular truetype, defaults are kept."""
    settings = default_display_settings()
    settings["text_font"] = "NoTTF"
    event = EventFactory(display_settings=settings)

    def handler(signal, sender, **kwargs):
        return {
            "NoTTF": {"regular": {"woff2": "fonts/mulish-v12-latin-ext-regular.woff2"}}
        }

    register_signal_handler(register_fonts, handler)
    _heading, text, text_italic = _resolve_fonts(event)

    assert text == "Muli"
    assert text_italic == "Muli-Italic"


@pytest.mark.django_db
def test_resolve_fonts_falls_back_when_font_not_in_plugins(register_signal_handler):
    """When display_settings reference fonts that no plugin provides, defaults are used."""
    settings = default_display_settings()
    settings["heading_font"] = "MissingFont"
    settings["text_font"] = "AlsoMissing"
    event = EventFactory(display_settings=settings)

    def handler(signal, sender, **kwargs):
        return {
            "OtherFont": {
                "regular": {"truetype": "fonts/mulish-v12-latin-ext-regular.ttf"}
            }
        }

    register_signal_handler(register_fonts, handler)
    heading, text, text_italic = _resolve_fonts(event)

    assert heading == "Titillium-Bold"
    assert text == "Muli"
    assert text_italic == "Muli-Italic"
