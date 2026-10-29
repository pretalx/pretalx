# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import re
from unittest.mock import Mock

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

from pretalx.common.signals import register_fonts
from pretalx.event.models.event import default_display_settings
from pretalx.submission.interfaces.cards import (
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
        ("é", None, "é"),
    ),
)
def test_text_normalizes_escapes_and_truncates(input_text, max_length, expected):
    assert _text(input_text, max_length) == expected


@pytest.mark.parametrize(
    ("duration", "expected_height"),
    (
        (10, 2.5 * 30 * mm),  # short durations clamped to 30 min
        (60, 2.5 * 60 * mm),  # actual duration used
        (9999, A4[1]),  # capped at A4 page height
    ),
)
def test_submission_card_init_height_and_bottom_up_coords(duration, expected_height):
    sub = Mock(get_duration=Mock(return_value=duration))
    card = SubmissionCard(
        sub,
        get_style("Titillium-Bold", "Muli", "Muli-Italic"),
        100 * mm,
        "Titillium-Bold",
    )
    assert card.height == expected_height
    assert card.coord(10, 20, unit=mm) == (10 * mm, expected_height - 20 * mm)


@pytest.mark.django_db
def test_get_story_creates_card_per_submission():
    subs = [Mock(get_duration=Mock(return_value=30)) for _ in range(3)]
    doc = Mock(width=A4[0])
    event = EventFactory()

    story = get_story(doc, subs, event)

    assert len(story) == 3
    assert all(isinstance(c, SubmissionCard) for c in story)
    assert all(c.width == doc.width / 2 for c in story)


@pytest.mark.django_db
def test_build_cards_returns_pdf():
    event = EventFactory()
    full = SubmissionFactory(event=event, abstract="An abstract", notes="Some notes")
    full.speakers.add(SpeakerFactory(event=event))
    bare = SubmissionFactory(event=event, abstract="", notes="")

    for submissions in ([full, bare], [bare]):
        response = build_cards(submissions, event)

        assert response["Content-Type"] == "application/pdf"
        assert re.fullmatch(
            rf'attachment; filename="{event.slug}_submission_cards_\d{{4}}-\d{{2}}-\d{{2}}-\d{{4}}\.pdf"',
            response["Content-Disposition"],
        )
        assert response.content.startswith(b"%PDF-")


@pytest.mark.parametrize(
    ("font_name", "font_data", "registered"),
    (
        (
            "TestPluginFont",
            {"regular": {"truetype": "fonts/mulish-v12-latin-ext-regular.ttf"}},
            {"regular"},
        ),
        (
            "TestMultiFont",
            {
                "regular": {"truetype": "fonts/mulish-v12-latin-ext-regular.ttf"},
                "italic": {"truetype": "fonts/mulish-v12-latin-ext-italic.ttf"},
                "bold": {"truetype": "fonts/titillium-web-v17-latin-ext-600.ttf"},
            },
            {"regular", "italic", "bold"},
        ),
        (
            "TestNoTTF",
            {"regular": {"woff2": "fonts/mulish-v12-latin-ext-regular.woff2"}},
            set(),
        ),
        ("TestBadPath", {"regular": {"truetype": "fonts/nonexistent-font.ttf"}}, set()),
        (
            "TestSampleFont",
            {
                "regular": {"truetype": "fonts/mulish-v12-latin-ext-regular.ttf"},
                "sample": "Example text",
            },
            {"regular"},
        ),
    ),
    ids=["regular", "variants", "no_truetype", "unresolvable", "non_dict_variant"],
)
def test_register_plugin_font(font_name, font_data, registered):
    assert _register_plugin_font(font_name, font_data) == registered


@pytest.mark.django_db
def test_resolve_fonts_returns_defaults_without_custom_fonts():
    defaults = ("Titillium-Bold", "Muli", "Muli-Italic")

    assert _resolve_fonts(None) == defaults
    assert _resolve_fonts(EventFactory()) == defaults


REGULAR = {"truetype": "fonts/mulish-v12-latin-ext-regular.ttf"}


@pytest.mark.parametrize(
    ("display_settings", "plugin_fonts", "expected"),
    (
        (
            {"heading_font": "CustomHeading"},
            {
                "CustomHeading": {
                    "regular": REGULAR,
                    "bold": {"truetype": "fonts/titillium-web-v17-latin-ext-600.ttf"},
                }
            },
            ("CustomHeading-Bold", "Muli", "Muli-Italic"),
        ),
        (
            {"heading_font": "CustomHeading"},
            {"CustomHeading": {"regular": REGULAR}},
            ("CustomHeading", "Muli", "Muli-Italic"),
        ),
        (
            {"text_font": "CustomText"},
            {
                "CustomText": {
                    "regular": REGULAR,
                    "italic": {"truetype": "fonts/mulish-v12-latin-ext-italic.ttf"},
                }
            },
            ("Titillium-Bold", "CustomText", "CustomText-Italic"),
        ),
        (
            {"text_font": "CustomText"},
            {"CustomText": {"regular": REGULAR}},
            ("Titillium-Bold", "CustomText", "CustomText"),
        ),
        (
            {"heading_font": "NoTTF", "text_font": "NoTTF"},
            {
                "NoTTF": {
                    "regular": {"woff2": "fonts/mulish-v12-latin-ext-regular.woff2"}
                }
            },
            ("Titillium-Bold", "Muli", "Muli-Italic"),
        ),
        (
            {"heading_font": "MissingFont", "text_font": "AlsoMissing"},
            {"OtherFont": {"regular": REGULAR}},
            ("Titillium-Bold", "Muli", "Muli-Italic"),
        ),
    ),
    ids=[
        "heading_with_bold",
        "heading_without_bold",
        "text_with_italic",
        "text_without_italic",
        "no_regular_truetype",
        "font_not_in_plugins",
    ],
)
@pytest.mark.django_db
def test_resolve_fonts_uses_plugin_fonts(
    register_signal_handler, display_settings, plugin_fonts, expected
):
    event = EventFactory(
        display_settings={**default_display_settings(), **display_settings}
    )

    def handler(signal, sender, **kwargs):
        return plugin_fonts

    register_signal_handler(register_fonts, handler)

    assert _resolve_fonts(event) == expected
