# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.submission.validators.review import (
    validate_non_independent_category_remains,
    validate_review_scores_present,
    validate_review_scores_unique_categories,
)
from tests.factories import EventFactory, ReviewScoreCategoryFactory, ReviewScoreFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_validate_non_independent_category_remains():
    event = EventFactory()
    event.score_categories.all().delete()
    only = ReviewScoreCategoryFactory(event=event, is_independent=False)

    with pytest.raises(ValidationError, match="at least one non-independent"):
        validate_non_independent_category_remains(only)

    ReviewScoreCategoryFactory(event=event, is_independent=False)
    validate_non_independent_category_remains(only)


@pytest.mark.parametrize(
    ("score_mandatory", "score_count"),
    ((True, 1), (False, 0)),
    ids=["required_and_provided", "not_required_and_missing"],
)
def test_validate_review_scores_present_accepts(score_mandatory, score_count):
    event = EventFactory(review_settings={"score_mandatory": score_mandatory})
    category = ReviewScoreCategoryFactory(event=event)
    scores = [ReviewScoreFactory(category=category) for _ in range(score_count)]

    validate_review_scores_present(event, scores)


def test_validate_review_scores_present_required_and_missing():
    event = EventFactory(review_settings={"score_mandatory": True})

    with pytest.raises(ValidationError, match="at least one review score"):
        validate_review_scores_present(event, [])


def test_validate_review_scores_unique_categories():
    cat_a = ReviewScoreCategoryFactory()
    cat_b = ReviewScoreCategoryFactory(event=cat_a.event)
    score_a = ReviewScoreFactory(category=cat_a, value=1)
    score_b = ReviewScoreFactory(category=cat_b)
    duplicate_a = ReviewScoreFactory(category=cat_a, value=2)

    validate_review_scores_unique_categories([score_a, score_b])
    with pytest.raises(ValidationError, match="one score per category"):
        validate_review_scores_unique_categories([score_a, duplicate_a])
