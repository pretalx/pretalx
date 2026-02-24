from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django_scopes import scope, scopes_disabled

from pretalx.submission.models import Review
from pretalx.submission.models.review import (
    ReviewPhase,
    ReviewScore,
    ReviewScoreCategory,
)
from tests.factories import (
    EventFactory,
    ReviewFactory,
    ReviewPhaseFactory,
    ReviewScoreCategoryFactory,
    ReviewScoreFactory,
    SubmissionFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_review_score_category_save_sets_weight_zero_when_independent():
    """Making an existing category independent sets weight to 0."""
    event = EventFactory()
    ReviewScoreCategoryFactory(event=event, is_independent=False)
    category = ReviewScoreCategoryFactory(event=event, is_independent=False)
    category.weight = Decimal("3.0")
    category.is_independent = True

    with scopes_disabled():
        category.save()

    assert category.weight == 0


@pytest.mark.django_db
def test_review_score_category_save_keeps_weight_when_not_independent():
    category = ReviewScoreCategoryFactory(is_independent=False, weight=Decimal("2.5"))

    with scopes_disabled():
        category.save()

    assert category.weight == Decimal("2.5")


@pytest.mark.django_db
def test_review_score_category_save_independent_validates_remaining_non_independent():
    """Cannot make a category independent if it's the only non-independent one."""
    event = EventFactory()
    with scopes_disabled():
        # Remove the default "Score" category created by build_initial_data
        event.score_categories.all().delete()
    category = ReviewScoreCategoryFactory(event=event, is_independent=False)

    category.is_independent = True
    with scopes_disabled(), pytest.raises(ValidationError):
        category.save()


@pytest.mark.django_db
def test_review_score_category_save_independent_allowed_with_other_non_independent():
    """Can make a category independent if another non-independent one exists."""
    event = EventFactory()
    ReviewScoreCategoryFactory(event=event, is_independent=False)
    category = ReviewScoreCategoryFactory(event=event, is_independent=False)

    category.is_independent = True
    with scopes_disabled():
        category.save()

    assert category.weight == 0


@pytest.mark.django_db
def test_review_score_category_save_new_independent_skips_validation():
    """New (unsaved) independent categories skip the independence validation."""
    event = EventFactory()
    category = ReviewScoreCategoryFactory(event=event, is_independent=True)

    assert category.pk is not None
    assert category.weight == 0


@pytest.mark.django_db
def test_review_score_category_delete_independent_validates():
    """Cannot delete an independent category if no other non-independent remains."""
    event = EventFactory()
    with scopes_disabled():
        # Remove the default "Score" category so only our independent one exists
        event.score_categories.all().delete()
    category = ReviewScoreCategoryFactory(event=event, is_independent=True)

    with scopes_disabled(), pytest.raises(ValidationError):
        category.delete()


@pytest.mark.django_db
def test_review_score_category_delete_non_independent_succeeds():
    """Can delete a non-independent category."""
    event = EventFactory()
    category = ReviewScoreCategoryFactory(event=event, is_independent=False)

    with scopes_disabled():
        count_before = event.score_categories.count()
        category.delete()
        assert event.score_categories.count() == count_before - 1


@pytest.mark.django_db
def test_review_score_category_recalculate_scores(event):
    """recalculate_scores updates all review scores for the event."""
    category = ReviewScoreCategoryFactory(event=event, weight=Decimal("1.0"))
    score = ReviewScoreFactory(category=category, value=Decimal(5))
    submission = SubmissionFactory(event=event)
    review = ReviewFactory(submission=submission, score=None)
    with scopes_disabled():
        review.scores.add(score)

    with scope(event=event):
        ReviewScoreCategory.recalculate_scores(event)

    with scopes_disabled():
        review.refresh_from_db()
    assert review.score == Decimal("5.0")


@pytest.mark.django_db
def test_review_score_category_limit_tracks():
    """limit_tracks M2M can be set and queried."""
    event = EventFactory()
    track = TrackFactory(event=event)
    category = ReviewScoreCategoryFactory(event=event)

    category.limit_tracks.add(track)

    with scopes_disabled():
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
@pytest.mark.django_db
def test_review_score_format(value, label, fmt, expected):
    score = ReviewScoreFactory(value=value, label=label)

    assert score.format(fmt) == expected


@pytest.mark.django_db
def test_review_score_str():
    """__str__ uses words_numbers format."""
    score = ReviewScoreFactory(value=Decimal(4), label="Great")

    assert str(score) == "Great (4)"


@pytest.mark.django_db
def test_review_score_ordering():
    """Scores are ordered by value."""
    category = ReviewScoreCategoryFactory()
    s1 = ReviewScoreFactory(category=category, value=Decimal(1))
    s2 = ReviewScoreFactory(category=category, value=Decimal(3))
    s3 = ReviewScoreFactory(category=category, value=Decimal(2))

    with scopes_disabled():
        result = list(ReviewScore.objects.filter(category=category))

    assert result == [s1, s3, s2]


@pytest.mark.django_db
def test_review_str():
    review = ReviewFactory(score=Decimal("3.0"))

    result = str(review)

    assert result == (
        f"Review(event={review.submission.event.slug}, "
        f"submission={review.submission.title}, "
        f"user={review.user.get_display_name}, score={review.score})"
    )


@pytest.mark.django_db
def test_review_log_parent():
    review = ReviewFactory()

    assert review.log_parent == review.submission


@pytest.mark.django_db
def test_review_event_delegates_to_submission():
    review = ReviewFactory()

    assert review.event == review.submission.event


@pytest.mark.parametrize(
    ("score", "expected"),
    ((None, "×"), (Decimal("3.0"), "3"), (Decimal("3.5"), "3.5")),
    ids=["none", "integer", "decimal"],
)
@pytest.mark.django_db
def test_review_display_score(score, expected):
    review = ReviewFactory(score=score)

    assert review.display_score == expected


def test_review_calculate_score_empty():
    assert Review.calculate_score([]) is None


@pytest.mark.django_db
def test_review_calculate_score_weighted():
    """calculate_score sums value * weight for each score."""
    category1 = ReviewScoreCategoryFactory(weight=Decimal("2.0"))
    category2 = ReviewScoreCategoryFactory(event=category1.event, weight=Decimal("1.0"))
    score1 = ReviewScoreFactory(category=category1, value=Decimal(5))
    score2 = ReviewScoreFactory(category=category2, value=Decimal(3))

    result = Review.calculate_score([score1, score2])

    assert result == Decimal("13.0")


@pytest.mark.django_db
def test_review_update_score(event):
    """update_score recalculates from the review's scores filtered by submission's score_categories."""
    category = ReviewScoreCategoryFactory(event=event, weight=Decimal("1.0"))
    score = ReviewScoreFactory(category=category, value=Decimal(7))
    submission = SubmissionFactory(event=event)
    review = ReviewFactory(submission=submission, score=None)
    with scopes_disabled():
        review.scores.add(score)

    with scopes_disabled():
        review.update_score()

    assert review.score == Decimal("7.0")


@pytest.mark.django_db
def test_review_save_updates_score(event):
    """Saving an existing review with update_score=True recalculates score."""
    category = ReviewScoreCategoryFactory(event=event, weight=Decimal("1.0"))
    score = ReviewScoreFactory(category=category, value=Decimal(4))
    submission = SubmissionFactory(event=event)
    review = ReviewFactory(submission=submission, score=None)
    with scopes_disabled():
        review.scores.add(score)

    with scopes_disabled():
        review.save(update_score=True)
    review.refresh_from_db()

    assert review.score == Decimal("4.0")


@pytest.mark.django_db
def test_review_save_skips_score_update_when_disabled(event):
    """Saving with update_score=False does not recalculate."""
    submission = SubmissionFactory(event=event)
    review = ReviewFactory(submission=submission, score=Decimal(99))

    with scopes_disabled():
        review.save(update_score=False)
    review.refresh_from_db()

    assert review.score == Decimal(99)


@pytest.mark.django_db
def test_review_save_skips_score_update_for_new_review(event):
    """New reviews (no pk yet) don't trigger update_score even if update_score=True."""
    submission = SubmissionFactory(event=event)
    user = UserFactory()
    with scopes_disabled():
        review = Review(submission=submission, user=user)
        review.score = Decimal(42)
        review.save(update_score=True)
        review.refresh_from_db()

    assert review.score == Decimal(42)


@pytest.mark.django_db
def test_review_unique_per_user_submission(event):
    """A user can only review a submission once."""
    submission = SubmissionFactory(event=event)
    review = ReviewFactory(submission=submission)

    with pytest.raises(IntegrityError):
        ReviewFactory(submission=submission, user=review.user)


@pytest.mark.django_db
def test_review_phase_activate_deactivates_others(event):
    phase1 = ReviewPhaseFactory(event=event, is_active=True)
    phase2 = ReviewPhaseFactory(event=event, is_active=False)

    with scopes_disabled():
        phase2.activate()

    phase1.refresh_from_db()
    phase2.refresh_from_db()
    assert phase1.is_active is False
    assert phase2.is_active is True


@pytest.mark.django_db
def test_review_phase_activate_deactivates_all_others(event):
    """Activating one phase deactivates all others, not just one."""
    phase1 = ReviewPhaseFactory(event=event, is_active=True)
    phase2 = ReviewPhaseFactory(event=event, is_active=False)
    phase3 = ReviewPhaseFactory(event=event, is_active=True)

    with scopes_disabled():
        phase2.activate()

    phase1.refresh_from_db()
    phase2.refresh_from_db()
    phase3.refresh_from_db()
    assert phase2.is_active is True
    assert phase1.is_active is False
    assert phase3.is_active is False


@pytest.mark.django_db
def test_review_phase_ordering(event):
    """Phases are ordered by position."""
    p3 = ReviewPhaseFactory(event=event, position=30)
    p1 = ReviewPhaseFactory(event=event, position=10)
    p2 = ReviewPhaseFactory(event=event, position=20)

    with scopes_disabled():
        result = list(
            ReviewPhase.objects.filter(event=event, pk__in=[p1.pk, p2.pk, p3.pk])
        )

    assert result == [p1, p2, p3]


@pytest.mark.django_db
def test_review_phase_get_order_queryset(event):
    """get_order_queryset returns all phases for the event, ordered by position."""
    with scopes_disabled():
        expected = list(event.review_phases.all().order_by("position"))
        result = list(ReviewPhase.get_order_queryset(event=event))

    assert result == expected


@pytest.mark.parametrize(
    ("move_first", "up", "expected_positions"),
    ((False, True, (1, 0)), (True, False, (1, 0))),
    ids=["move_up", "move_down"],
)
@pytest.mark.django_db
def test_review_phase_move(event, move_first, up, expected_positions):
    """Moving a phase swaps it with its neighbor."""
    with scopes_disabled():
        event.review_phases.all().delete()
    phase1 = ReviewPhaseFactory(event=event, position=0)
    phase2 = ReviewPhaseFactory(event=event, position=1)

    target = phase1 if move_first else phase2
    with scopes_disabled():
        target.move(up=up)

    phase1.refresh_from_db()
    phase2.refresh_from_db()
    assert (phase1.position, phase2.position) == expected_positions
