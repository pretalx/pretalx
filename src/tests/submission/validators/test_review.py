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


def test_validator_raises_when_self_is_only_non_independent():
    """The category being validated is excluded from the count of remaining ones."""
    event = EventFactory()
    event.score_categories.all().delete()
    only = ReviewScoreCategoryFactory(event=event, is_independent=False)

    with pytest.raises(ValidationError):
        validate_non_independent_category_remains(only)


def test_validator_passes_when_another_non_independent_exists():
    event = EventFactory()
    ReviewScoreCategoryFactory(event=event, is_independent=False)
    other = ReviewScoreCategoryFactory(event=event, is_independent=False)

    validate_non_independent_category_remains(other)


def test_validate_review_scores_present_required_and_missing():
    event = EventFactory(review_settings={"score_mandatory": True})

    with pytest.raises(ValidationError, match="at least one review score"):
        validate_review_scores_present(event, [])


def test_validate_review_scores_present_required_and_provided():
    event = EventFactory(review_settings={"score_mandatory": True})
    category = ReviewScoreCategoryFactory(event=event)
    score = ReviewScoreFactory(category=category)

    validate_review_scores_present(event, [score])


def test_validate_review_scores_present_not_required_and_missing():
    event = EventFactory(review_settings={"score_mandatory": False})

    validate_review_scores_present(event, [])


def test_validate_review_scores_unique_categories_passes_for_distinct():
    cat_a = ReviewScoreCategoryFactory()
    cat_b = ReviewScoreCategoryFactory(event=cat_a.event)
    score_a = ReviewScoreFactory(category=cat_a)
    score_b = ReviewScoreFactory(category=cat_b)

    validate_review_scores_unique_categories([score_a, score_b])


def test_validate_review_scores_unique_categories_raises_for_duplicate():
    category = ReviewScoreCategoryFactory()
    score_a = ReviewScoreFactory(category=category, value=1)
    score_b = ReviewScoreFactory(category=category, value=2)

    with pytest.raises(ValidationError, match="one score per category"):
        validate_review_scores_unique_categories([score_a, score_b])
