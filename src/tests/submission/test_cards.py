from unittest.mock import Mock

import pytest
from django_scopes import scopes_disabled
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

from pretalx.submission.cards import (
    SubmissionCard,
    _text,
    build_cards,
    get_story,
    get_style,
)
from tests.factories import SpeakerFactory, SubmissionFactory

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
    card = SubmissionCard(sub, get_style(), 100 * mm)
    assert card.height == expected_height


def test_submission_card_coord_transforms_to_bottom_up():
    sub = Mock(get_duration=Mock(return_value=30))
    card = SubmissionCard(sub, get_style(), 100 * mm)
    x, y = card.coord(10, 20, unit=mm)
    assert x == 10 * mm
    assert y == card.height - 20 * mm


def test_get_story_creates_card_per_submission():
    subs = [Mock(get_duration=Mock(return_value=30)) for _ in range(3)]
    doc = Mock(width=A4[0])

    story = get_story(doc, subs)

    assert len(story) == 3
    assert all(isinstance(c, SubmissionCard) for c in story)
    assert all(c.width == doc.width / 2 for c in story)


@pytest.mark.parametrize(
    ("abstract", "notes"), (("An abstract", "Some notes"), ("", ""))
)
@pytest.mark.django_db
def test_build_cards_returns_pdf(event, abstract, notes):
    """Exercises SubmissionCard.draw with and without abstract/notes branches."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event, abstract=abstract, notes=notes)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)

    with scopes_disabled():
        response = build_cards([submission], event)

    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].startswith("attachment;")
    assert event.slug in response["Content-Disposition"]
    assert len(response.content) > 0
