# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import types

import pytest

from pretalx.orga.templatetags.review_score import _review_score_number, review_score

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("score", "expected"), ((3, "3"), (0, "0"), (3.0, "3"), (1.5, "1.5"), (None, "×"))
)
def test_review_score_number_with_context(score, expected):
    assert _review_score_number({"event": "something"}, score) == expected


@pytest.mark.parametrize(
    ("score", "expected"), ((3, "3"), (1.5, "1.5"), (3.0, "3.0"), (None, "×"))
)
def test_review_score_number_without_context(score, expected):
    assert _review_score_number(None, score) == expected


def test_review_score_picks_current_or_user_score():
    scored = types.SimpleNamespace(current_score=4.2, user_score=1.0)
    unscored = types.SimpleNamespace(current_score=None, user_score=None)

    assert review_score({"event": "ctx"}, scored) == "4.2"
    assert review_score({"event": "ctx"}, scored, user_score=True) == "1"
    assert review_score({}, unscored) == "-"
    assert review_score({}, unscored, user_score=True) == "-"
