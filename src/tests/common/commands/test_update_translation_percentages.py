# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.conf import settings

from pretalx.common.management.commands.update_translation_percentages import (
    get_language_scores,
)

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def language_scores():
    """Shared fixture: get_language_scores() reads every .po file from disk,
    so we call it once and reuse the result across all tests in this module."""
    return get_language_scores()


def test_get_language_scores_returns_all_configured_languages(language_scores):
    assert set(language_scores.keys()) == set(settings.LANGUAGES_INFORMATION.keys())


def test_get_language_scores_english_is_always_100(language_scores):
    assert language_scores["en"] == 100


def test_get_language_scores_values_are_valid_percentages(language_scores):
    for lang, score in language_scores.items():
        assert 0 <= score <= 100, f"{lang} has score {score}"


def test_get_language_scores_german_is_translated(language_scores):
    """German is actively maintained, so it must have some translations."""
    assert language_scores["de"] > 0
