# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from pretalx.submission.models.review import ReviewPhase, ReviewScore
from tests.factories import (
    EventFactory,
    ReviewFactory,
    ReviewPhaseFactory,
    ReviewScoreCategoryFactory,
    ReviewScoreFactory,
    SubmissionFactory,
    TrackFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_review_score_category_save_sets_weight_zero_when_independent():
    event = EventFactory()
    ReviewScoreCategoryFactory(event=event, is_independent=False)
    category = ReviewScoreCategoryFactory(event=event, is_independent=False)
    category.weight = Decimal("3.0")
    category.is_independent = True

    category.save()

    assert category.weight == 0


def test_review_score_category_save_keeps_weight_when_not_independent():
    category = ReviewScoreCategoryFactory(is_independent=False, weight=Decimal("2.5"))

    category.save()

    assert category.weight == Decimal("2.5")


def test_review_score_category_clean_independent_validates_remaining_non_independent():
    event = EventFactory()
    event.score_categories.all().delete()
    category = ReviewScoreCategoryFactory(event=event, is_independent=False)

    category.is_independent = True
    with pytest.raises(ValidationError):
        category.full_clean()


def test_review_score_category_clean_independent_allowed_with_other_non_independent():
    event = EventFactory()
    ReviewScoreCategoryFactory(event=event, is_independent=False)
    category = ReviewScoreCategoryFactory(event=event, is_independent=False)

    category.is_independent = True
    category.full_clean()
    category.save()

    assert category.weight == 0


def test_review_score_category_clean_new_independent_skips_validation():
    event = EventFactory()
    category = ReviewScoreCategoryFactory(event=event, is_independent=True)

    assert category.pk is not None
    assert category.weight == 0


def test_review_score_category_delete_independent_validates():
    event = EventFactory()
    event.score_categories.all().delete()
    category = ReviewScoreCategoryFactory(event=event, is_independent=True)

    with pytest.raises(ValidationError):
        category.delete()


def test_review_score_category_delete_non_independent_succeeds():
    event = EventFactory()
    category = ReviewScoreCategoryFactory(event=event, is_independent=False)

    count_before = event.score_categories.count()
    category.delete()
    assert event.score_categories.count() == count_before - 1


def test_review_score_category_limit_tracks():
    event = EventFactory()
    track = TrackFactory(event=event)
    category = ReviewScoreCategoryFactory(event=event)

    category.limit_tracks.add(track)

    assert list(category.limit_tracks.all()) == [track]


@pytest.mark.parametrize(
    ("value", "label", "fmt", "expected"),
    (
        (Decimal(3), "Good", "words", "Good"),
        (Decimal(3), "Good", "numbers", "3"),
        (Decimal("3.5"), "Good", "numbers", "3.5"),
        (Decimal(3), "Good", "words_numbers", "Good (3)"),
        (Decimal("3.5"), "Good", "words_numbers", "Good (3.5)"),
        (Decimal(3), "Good", "numbers_words", "3 (Good)"),
        (Decimal("3.5"), "Good", "numbers_words", "3.5 (Good)"),
        (Decimal(3), "3", "words_numbers", "3"),
    ),
    ids=[
        "words",
        "numbers_int",
        "numbers_decimal",
        "words_numbers_int",
        "words_numbers_decimal",
        "numbers_words_int",
        "numbers_words_decimal",
        "label_equals_value",
    ],
)
def test_review_score_format(value, label, fmt, expected):
    score = ReviewScoreFactory(value=value, label=label)

    assert score.format(fmt) == expected


def test_review_score_str():
    score = ReviewScoreFactory(value=Decimal(4), label="Great")

    assert str(score) == "Great (4)"


def test_review_score_ordering():
    category = ReviewScoreCategoryFactory()
    s1 = ReviewScoreFactory(category=category, value=Decimal(1))
    s2 = ReviewScoreFactory(category=category, value=Decimal(3))
    s3 = ReviewScoreFactory(category=category, value=Decimal(2))

    result = list(ReviewScore.objects.filter(category=category))

    assert result == [s1, s3, s2]


def test_review_str():
    review = ReviewFactory(score=Decimal("3.0"))

    result = str(review)

    assert result == (
        f"Review(event={review.submission.event.slug}, "
        f"submission={review.submission.title}, "
        f"user={review.user.get_display_name}, score={review.score})"
    )


def test_review_log_parent():
    review = ReviewFactory()

    assert review.log_parent == review.submission


def test_review_event_delegates_to_submission():
    review = ReviewFactory()

    assert review.event == review.submission.event


@pytest.mark.parametrize(
    ("score", "expected"),
    ((None, "×"), (Decimal("3.0"), "3"), (Decimal("3.5"), "3.5")),
    ids=["none", "integer", "decimal"],
)
def test_review_display_score(score, expected):
    review = ReviewFactory(score=score)

    assert review.display_score == expected


def test_review_unique_per_user_submission():
    submission = SubmissionFactory()
    review = ReviewFactory(submission=submission)

    with pytest.raises(IntegrityError):
        ReviewFactory(submission=submission, user=review.user)


def test_review_phase_ordering():
    event = EventFactory()
    p3 = ReviewPhaseFactory(event=event, position=30)
    p1 = ReviewPhaseFactory(event=event, position=10)
    p2 = ReviewPhaseFactory(event=event, position=20)

    result = list(ReviewPhase.objects.filter(event=event, pk__in=[p1.pk, p2.pk, p3.pk]))

    assert result == [p1, p2, p3]


def test_review_phase_get_order_queryset():
    event = EventFactory()
    expected = list(event.review_phases.all().order_by("position"))
    result = list(ReviewPhase.get_order_queryset(event=event))

    assert result == expected


@pytest.mark.parametrize(
    ("move_first", "up", "expected_positions"),
    ((False, True, (1, 0)), (True, False, (1, 0))),
    ids=["move_up", "move_down"],
)
def test_review_phase_move(move_first, up, expected_positions):
    event = EventFactory()
    event.review_phases.all().delete()
    phase1 = ReviewPhaseFactory(event=event, position=0)
    phase2 = ReviewPhaseFactory(event=event, position=1)

    target = phase1 if move_first else phase2
    target.move(up=up)

    phase1.refresh_from_db()
    phase2.refresh_from_db()
    assert (phase1.position, phase2.position) == expected_positions
