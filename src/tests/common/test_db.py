import pytest
from django_scopes import scopes_disabled

from pretalx.common.db import Median
from pretalx.submission.models import Review
from tests.factories import ReviewFactory, SubmissionFactory

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("scores", "expected"), (([], None), ([4], 4.0), ([3, 7], 5.0))
)
@pytest.mark.django_db
def test_median_aggregate(scores, expected):
    """On SQLite, Median falls back to AVG. Verify it runs and returns the expected value."""
    if scores:
        sub = SubmissionFactory()
        for score in scores:
            ReviewFactory(submission=sub, score=score)

    with scopes_disabled():
        result = Review.objects.aggregate(median_score=Median("score"))

    assert result["median_score"] == expected
