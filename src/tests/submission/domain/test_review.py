# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
from decimal import Decimal

import pytest
from django.utils.timezone import now as tz_now
from django_scopes import scope

from pretalx.common.models import ActivityLog
from pretalx.submission.domain.review import (
    activate_review_phase,
    recalculate_event_scores,
    recalculate_submission_scores,
    update_review_phase,
    update_review_score,
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


def test_update_review_score_empty():
    submission = SubmissionFactory()
    review = ReviewFactory(submission=submission, score=Decimal(99))

    update_review_score(review)
    review.refresh_from_db()

    assert review.score is None


def test_update_review_score_weighted():
    event = EventFactory()
    category1 = ReviewScoreCategoryFactory(event=event, weight=Decimal("2.0"))
    category2 = ReviewScoreCategoryFactory(event=event, weight=Decimal("1.0"))
    score1 = ReviewScoreFactory(category=category1, value=Decimal(5))
    score2 = ReviewScoreFactory(category=category2, value=Decimal(3))
    submission = SubmissionFactory(event=event)
    review = ReviewFactory(submission=submission, score=None)
    review.scores.add(score1, score2)

    update_review_score(review)
    review.refresh_from_db()

    assert review.score == Decimal("13.0")


def test_update_review_score_persists():
    event = EventFactory()
    category = ReviewScoreCategoryFactory(event=event, weight=Decimal("1.0"))
    score = ReviewScoreFactory(category=category, value=Decimal(7))
    submission = SubmissionFactory(event=event)
    review = ReviewFactory(submission=submission, score=None)
    review.scores.add(score)

    update_review_score(review)
    review.refresh_from_db()

    assert review.score == Decimal("7.0")


def test_update_review_score_filters_by_submission_categories():
    """Categories not applicable to the submission's track are ignored."""
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    other_track = submission.event.tracks.create(name="Other")
    excluded = ReviewScoreCategoryFactory(event=event, weight=Decimal("1.0"))
    excluded.limit_tracks.add(other_track)
    excluded_score = ReviewScoreFactory(category=excluded, value=Decimal(99))
    review = ReviewFactory(submission=submission, score=None)
    review.scores.add(excluded_score)

    update_review_score(review)
    review.refresh_from_db()

    assert review.score is None


def test_recalculate_event_scores():
    event = EventFactory()
    category = ReviewScoreCategoryFactory(event=event, weight=Decimal("1.0"))
    score = ReviewScoreFactory(category=category, value=Decimal(5))
    submission = SubmissionFactory(event=event)
    review = ReviewFactory(submission=submission, score=None)
    review.scores.add(score)

    with scope(event=event):
        recalculate_event_scores(event)

    review.refresh_from_db()
    assert review.score == Decimal("5.0")


def test_recalculate_submission_scores():
    event = EventFactory()
    category = ReviewScoreCategoryFactory(event=event, weight=Decimal("1.0"))
    score = ReviewScoreFactory(category=category, value=Decimal(4))
    submission = SubmissionFactory(event=event)
    review = ReviewFactory(submission=submission, score=None)
    review.scores.add(score)

    with scope(event=event):
        recalculate_submission_scores(submission)

    review.refresh_from_db()
    assert review.score == Decimal("4.0")


def test_activate_review_phase_deactivates_others():
    event = EventFactory()
    phase1 = ReviewPhaseFactory(event=event, is_active=True)
    phase2 = ReviewPhaseFactory(event=event, is_active=False)

    activate_review_phase(phase2)

    phase1.refresh_from_db()
    phase2.refresh_from_db()
    assert phase1.is_active is False
    assert phase2.is_active is True


def test_activate_review_phase_deactivates_all_others():
    event = EventFactory()
    phase1 = ReviewPhaseFactory(event=event, is_active=True)
    phase2 = ReviewPhaseFactory(event=event, is_active=False)
    phase3 = ReviewPhaseFactory(event=event, is_active=True)

    activate_review_phase(phase2)

    phase1.refresh_from_db()
    phase2.refresh_from_db()
    phase3.refresh_from_db()
    assert phase2.is_active is True
    assert phase1.is_active is False
    assert phase3.is_active is False


def test_activate_review_phase_logs_with_phase_name():
    event = EventFactory()
    phase = ReviewPhaseFactory(event=event, name="Final review")
    user = UserFactory()

    activate_review_phase(phase, person=user)

    log = ActivityLog.objects.get(action_type="pretalx.review_phase.activate")
    assert log.event == event
    assert log.person == user
    assert log.is_orga_action is True
    assert log.data["name"] == "Final review"


def test_update_review_phase_keeps_current_when_valid(event):
    with scope(event=event):
        event.review_phases.all().delete()
        phase = ReviewPhaseFactory(
            event=event,
            name="Active",
            start=tz_now() - dt.timedelta(days=1),
            end=tz_now() + dt.timedelta(days=30),
            is_active=True,
        )

    event = refresh(event)
    with scope(event=event):
        result = update_review_phase(event)
        assert result == phase


def test_update_review_phase_deactivates_expired(event):
    """update_review_phase deactivates an expired phase and returns None
    when no successor is available."""
    with scope(event=event):
        event.review_phases.all().delete()
        phase = ReviewPhaseFactory(
            event=event,
            name="Expired",
            start=tz_now() - dt.timedelta(days=10),
            end=tz_now() - dt.timedelta(days=3),
            is_active=True,
        )

    event = refresh(event)
    with scope(event=event):
        result = update_review_phase(event)
        assert result is None
        phase.refresh_from_db()
        assert not phase.is_active


def test_update_review_phase_activates_next(event):
    with scope(event=event):
        event.review_phases.all().delete()
        expired_phase = ReviewPhaseFactory(
            event=event,
            name="Expired",
            start=tz_now() - dt.timedelta(days=10),
            end=tz_now() - dt.timedelta(days=3),
            is_active=True,
        )
        next_phase = ReviewPhaseFactory(
            event=event, name="Next", start=expired_phase.end, is_active=False
        )

    event = refresh(event)
    with scope(event=event):
        result = update_review_phase(event)
        assert result == next_phase
        next_phase.refresh_from_db()
        assert next_phase.is_active


def test_update_review_phase_deactivates_future_phase(event):
    with scope(event=event):
        event.review_phases.all().delete()
        future_phase = ReviewPhaseFactory(
            event=event,
            name="Future",
            start=tz_now() + dt.timedelta(days=30),
            is_active=True,
        )

    event = refresh(event)
    with scope(event=event):
        result = update_review_phase(event)
        assert result is None
        future_phase.refresh_from_db()
        assert not future_phase.is_active
