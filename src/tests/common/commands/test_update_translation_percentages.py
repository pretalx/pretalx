# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.conf import settings

from pretalx.common.management.commands.update_translation_percentages import (
    get_language_scores,
)

pytestmark = pytest.mark.unit


def test_get_language_scores():
    scores = get_language_scores()

    assert set(scores.keys()) == set(settings.LANGUAGES_INFORMATION.keys())
    assert scores["en"] == 100
    assert scores["de"] > 0
    for lang, score in scores.items():
        assert 0 <= score <= 100, f"{lang} has score {score}"
