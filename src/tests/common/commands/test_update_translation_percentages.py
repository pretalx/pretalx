import pytest
from django.conf import settings

from pretalx.common.management.commands.update_translation_percentages import (
    get_language_scores,
)

pytestmark = pytest.mark.unit


def test_get_language_scores_returns_all_configured_languages():
    scores = get_language_scores()

    assert set(scores.keys()) == set(settings.LANGUAGES_INFORMATION.keys())


def test_get_language_scores_english_is_always_100():
    scores = get_language_scores()

    assert scores["en"] == 100


def test_get_language_scores_values_are_valid_percentages():
    scores = get_language_scores()

    for lang, score in scores.items():
        assert 0 <= score <= 100, f"{lang} has score {score}"


def test_get_language_scores_german_is_translated():
    """German is actively maintained, so it must have some translations."""
    scores = get_language_scores()

    assert scores["de"] > 0
