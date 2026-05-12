# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from decimal import Decimal

import pytest
from django_scopes import scope

from pretalx.submission.domain.queries.review import (
    annotate_aggregate_scores,
    annotate_review_count,
    annotate_scored_review_count,
    annotate_state_rank,
    annotate_user_review_score,
    review_dashboard_prefetches,
    review_view_submissions,
)
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    EventFactory,
    ResourceFactory,
    ReviewFactory,
    SpeakerFactory,
    SubmissionFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_annotate_review_count():
    event = EventFactory()
    s1 = SubmissionFactory(event=event)
    s2 = SubmissionFactory(event=event)
    ReviewFactory(submission=s1)
    ReviewFactory(submission=s1)
    ReviewFactory(submission=s2)

    with scope(event=event):
        result = {
            row.pk: row.review_count
            for row in annotate_review_count(event.submissions.all())
        }

    assert result[s1.pk] == 2
    assert result[s2.pk] == 1


def test_annotate_review_count_zero_for_unreviewed():
    event = EventFactory()
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        row = annotate_review_count(event.submissions.all()).get(pk=submission.pk)

    assert row.review_count == 0


def test_annotate_scored_review_count_only_counts_scored():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    ReviewFactory(submission=submission, score=Decimal(5))
    ReviewFactory(submission=submission, score=None)

    with scope(event=event):
        row = annotate_scored_review_count(event.submissions.all()).get(
            pk=submission.pk
        )

    assert row.review_nonnull_count == 1


def test_annotate_user_review_score():
    event = EventFactory()
    user = UserFactory()
    other = UserFactory()
    submission = SubmissionFactory(event=event)
    ReviewFactory(submission=submission, user=user, score=Decimal(7))
    ReviewFactory(submission=submission, user=other, score=Decimal(1))

    with scope(event=event):
        row = annotate_user_review_score(event.submissions.all(), user).get(
            pk=submission.pk
        )

    assert row.user_score == Decimal(7)


def test_annotate_user_review_score_no_review():
    event = EventFactory()
    user = UserFactory()
    submission = SubmissionFactory(event=event)

    with scope(event=event):
        row = annotate_user_review_score(event.submissions.all(), user).get(
            pk=submission.pk
        )

    assert row.user_score is None


def test_annotate_aggregate_scores_returns_mean_and_median():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    ReviewFactory(submission=submission, score=Decimal(4))
    ReviewFactory(submission=submission, score=Decimal(6))
    ReviewFactory(submission=submission, score=None)

    with scope(event=event):
        row = annotate_aggregate_scores(event.submissions.all()).get(pk=submission.pk)

    assert row.mean_score == Decimal(5)
    assert row.median_score == Decimal(5)


def test_annotate_state_rank_orders_states():
    event = EventFactory()
    submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    confirmed = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    rejected = SubmissionFactory(event=event, state=SubmissionStates.REJECTED)

    with scope(event=event):
        ranks = {
            row.pk: row.state_rank
            for row in annotate_state_rank(event.submissions.all())
        }

    assert ranks[submitted.pk] == 1
    assert ranks[accepted.pk] == 2
    assert ranks[confirmed.pk] == 3
    assert ranks[rejected.pk] == 4


def test_annotate_state_rank_default_for_other_states():
    event = EventFactory()
    withdrawn = SubmissionFactory(event=event, state=SubmissionStates.WITHDRAWN)

    with scope(event=event):
        row = annotate_state_rank(event.submissions.all()).get(pk=withdrawn.pk)

    assert row.state_rank == 5


def test_review_dashboard_prefetches_returns_queryset():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    ReviewFactory(submission=submission)

    with scope(event=event):
        # Force evaluation so the prefetch chain actually runs.
        rows = list(review_dashboard_prefetches(event.submissions.all()))

    assert len(rows) == 1
    assert rows[0].pk == submission.pk


def test_review_view_submissions_prefetches_related_data():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    ResourceFactory(submission=submission)
    # An additional submission for the same speaker, exercised by the
    # speakers__submissions Prefetch.
    other = SubmissionFactory(event=event)
    other.speakers.add(speaker)

    with scope(event=event):
        result = review_view_submissions(event).get(pk=submission.pk)
        speaker_subs = list(result.speakers.first().submissions.all())

    assert {sub.pk for sub in speaker_subs} == {submission.pk, other.pk}
