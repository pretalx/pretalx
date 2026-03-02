# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.common.db import Median
from pretalx.submission.models import Review
from tests.factories import ReviewFactory, SubmissionFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("scores", "expected"), (([], None), ([4], 4.0), ([3, 7], 5.0))
)
def test_median_aggregate(scores, expected):
    """On SQLite, Median falls back to AVG. Verify it runs and returns the expected value."""
    if scores:
        sub = SubmissionFactory()
        for score in scores:
            ReviewFactory(submission=sub, score=score)

    result = Review.objects.aggregate(median_score=Median("score"))

    assert result["median_score"] == expected
