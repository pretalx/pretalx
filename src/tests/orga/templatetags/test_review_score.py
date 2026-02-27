import types

import pytest

from pretalx.orga.templatetags.review_score import _review_score_number, review_score

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("score", "expected"), ((3, "3"), (0, "0"), (3.0, "3"), (1.5, "1.5"), (None, "×"))
)
def test_review_score_number_with_context(score, expected):
    """With a truthy context, integer-valued floats are displayed without decimals."""
    assert _review_score_number({"event": "something"}, score) == expected


@pytest.mark.parametrize(
    ("score", "expected"), ((3, "3"), (1.5, "1.5"), (3.0, "3.0"), (None, "×"))
)
def test_review_score_number_without_context(score, expected):
    """Without context (falsy), floats keep their decimal representation."""
    assert _review_score_number(None, score) == expected


def test_review_score_returns_dash_when_score_is_none():
    submission = types.SimpleNamespace(current_score=None, user_score=None)

    assert review_score({}, submission) == "-"
    assert review_score({}, submission, user_score=True) == "-"


def test_review_score_uses_current_score_by_default():
    submission = types.SimpleNamespace(current_score=4.2, user_score=1.0)

    result = review_score({"event": "ctx"}, submission)
    assert result == "4.2"


def test_review_score_uses_user_score_when_flag_set():
    submission = types.SimpleNamespace(current_score=4.2, user_score=1.0)

    result = review_score({"event": "ctx"}, submission, user_score=True)
    assert result == "1"
