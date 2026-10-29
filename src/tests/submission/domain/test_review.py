# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils.timezone import now as tz_now
from django_scopes import scope

from pretalx.common.models import ActivityLog
from pretalx.submission.domain.review import (
    activate_review_phase,
    create_or_update_review,
    recalculate_event_scores,
    recalculate_submission_scores,
    update_review_phase,
    update_review_score,
    validate_review_phases,
)
from tests.factories import (
    EventFactory,
    ReviewFactory,
    ReviewPhaseFactory,
    ReviewScoreCategoryFactory,
    ReviewScoreFactory,
    SubmissionFactory,
    UserFactory,
)
from tests.utils import refresh

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_create_or_update_review_creates_updates_and_clears_scores():
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event)
    category = ReviewScoreCategoryFactory(event=event, weight=Decimal("1.0"))
    old_score = ReviewScoreFactory(category=category, value=Decimal(3))
    new_score = ReviewScoreFactory(category=category, value=Decimal(2))

    review = create_or_update_review(
        submission=submission, user=user, text="Nice talk", scores=[old_score]
    )

    assert list(submission.reviews.all()) == [review]
    assert review.user == user
    assert review.text == "Nice talk"
    assert list(review.scores.all()) == [old_score]
    assert review.score == Decimal("3.0")

    updated = create_or_update_review(
        submission=submission, user=user, text="Second save", scores=[new_score]
    )

    assert updated.pk == review.pk
    assert updated.created == review.created
    assert updated.text == "Second save"
    assert list(updated.scores.all()) == [new_score]
    assert updated.score == Decimal("2.0")
    assert list(submission.reviews.all()) == [updated]

    cleared = create_or_update_review(
        submission=submission, user=user, text="No more score", scores=[]
    )

    assert cleared.pk == review.pk
    assert list(cleared.scores.all()) == []
    assert cleared.score is None


def test_update_review_score_weights_applicable_categories():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    category1 = ReviewScoreCategoryFactory(event=event, weight=Decimal("2.0"))
    category2 = ReviewScoreCategoryFactory(event=event, weight=Decimal("1.0"))
    excluded = ReviewScoreCategoryFactory(event=event, weight=Decimal("1.0"))
    excluded.limit_tracks.add(event.tracks.create(name="Other"))
    review = ReviewFactory(submission=submission, score=Decimal(99))

    update_review_score(review)
    review.refresh_from_db(fields=["score"])
    assert review.score is None

    review.scores.add(ReviewScoreFactory(category=excluded, value=Decimal(99)))
    update_review_score(review)
    review.refresh_from_db(fields=["score"])
    assert review.score is None

    review.scores.add(
        ReviewScoreFactory(category=category1, value=Decimal(5)),
        ReviewScoreFactory(category=category2, value=Decimal(3)),
    )
    update_review_score(review)
    review.refresh_from_db(fields=["score"])
    assert review.score == Decimal("13.0")

    with scope(event=event):
        review.score = None
        review.save()
        recalculate_event_scores(event)
        review.refresh_from_db(fields=["score"])
        assert review.score == Decimal("13.0")

        review.score = None
        review.save()
        recalculate_submission_scores(submission)
        review.refresh_from_db(fields=["score"])
        assert review.score == Decimal("13.0")


def test_activate_review_phase_deactivates_others_and_logs():
    event = EventFactory()
    phase1 = ReviewPhaseFactory(event=event, is_active=True)
    phase2 = ReviewPhaseFactory(event=event, is_active=False, name="Final review")
    phase3 = ReviewPhaseFactory(event=event, is_active=True)
    user = UserFactory()

    activate_review_phase(phase2, person=user)

    assert list(event.review_phases.filter(is_active=True)) == [phase2]
    assert phase1 not in event.review_phases.filter(is_active=True)
    assert phase3 not in event.review_phases.filter(is_active=True)
    log = ActivityLog.objects.select_related("event", "person").get(
        action_type="pretalx.review_phase.activate"
    )
    assert log.event == event
    assert log.person == user
    assert log.is_orga_action is True
    assert log.data == {"name": "Final review"}


def _phases(event, specs):
    moment = tz_now()
    for name, start, end, is_active in specs:
        ReviewPhaseFactory(
            event=event,
            name=name,
            start=None if start is None else moment + dt.timedelta(days=start),
            end=None if end is None else moment + dt.timedelta(days=end),
            is_active=is_active,
        )


@pytest.mark.parametrize(
    ("specs", "expected"),
    (
        ((("Active", -1, 30, True),), "Active"),
        ((("Expired", -10, -3, True),), None),
        ((("Expired", -10, -3, True), ("Next", -3, None, False)), "Next"),
        ((("Available", -1, 30, False),), "Available"),
        ((("Future", 30, None, False),), None),
        ((("Future", 30, None, True),), None),
    ),
    ids=(
        "keeps_current",
        "deactivates_expired",
        "activates_next",
        "activates_when_none_active",
        "none_when_none_due",
        "deactivates_future",
    ),
)
def test_update_review_phase(event, specs, expected):
    with scope(event=event):
        event.review_phases.all().delete()
        _phases(event, specs)

    event = refresh(event)
    with scope(event=event):
        result = update_review_phase(event)
        assert (result.name if result else None) == expected
        assert [phase.name for phase in event.review_phases.filter(is_active=True)] == (
            [expected] if expected else []
        )


def _phase_errors(event):
    try:
        validate_review_phases(event)
    except ValidationError as exc:
        return exc.messages
    return []


@pytest.mark.parametrize(
    ("specs", "errors"),
    (
        ((("First", -10, -5, False), ("Second", -4, None, False)), []),
        (
            (("First", None, None, False), ("Second", 0, 1, False)),
            ["Only the last review phase may be open-ended."],
        ),
        (
            (("First", None, -10, False), ("Second", None, -5, False)),
            ["All review phases except for the first one need a start date."],
        ),
        (
            (("First", -10, 5, False), ("Second", -1, 10, False)),
            [
                (
                    "The review phases 'First' and 'Second' overlap. Please make sure "
                    "that review phases do not overlap, then save again."
                )
            ],
        ),
    ),
    ids=("ordered", "open_ended_non_last", "missing_start_non_first", "overlap"),
)
def test_validate_review_phases(event, specs, errors):
    # Phases are ordered (start asc, end asc, nulls first): two null-start
    # phases with non-null ends put the earlier end first.
    with scope(event=event):
        event.review_phases.all().delete()
        _phases(event, specs)

    event = refresh(event)
    with scope(event=event):
        assert _phase_errors(event) == errors
