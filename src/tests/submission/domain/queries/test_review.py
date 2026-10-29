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
    review_view_submissions,
)
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    EventFactory,
    ResourceFactory,
    ReviewFactory,
    SpeakerFactory,
    SubmissionFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _by_pk(queryset, attribute):
    return {row.pk: getattr(row, attribute) for row in queryset}


def test_annotate_review_counts_and_scores():
    event = EventFactory()
    user = UserFactory()
    reviewed = SubmissionFactory(event=event)
    unreviewed = SubmissionFactory(event=event)
    ReviewFactory(submission=reviewed, user=user, score=Decimal(7))
    ReviewFactory(submission=reviewed, score=Decimal(1))
    ReviewFactory(submission=reviewed, score=None)

    with scope(event=event):
        submissions = event.submissions.all()
        assert _by_pk(annotate_review_count(submissions), "review_count") == {
            reviewed.pk: 3,
            unreviewed.pk: 0,
        }
        assert _by_pk(
            annotate_scored_review_count(submissions), "review_nonnull_count"
        ) == {reviewed.pk: 2, unreviewed.pk: 0}
        assert _by_pk(annotate_user_review_score(submissions, user), "user_score") == {
            reviewed.pk: Decimal(7),
            unreviewed.pk: None,
        }
        assert _by_pk(
            annotate_user_review_score(submissions, UserFactory()), "user_score"
        ) == {reviewed.pk: None, unreviewed.pk: None}
        aggregated = {
            row.pk: (row.mean_score, row.median_score)
            for row in annotate_aggregate_scores(submissions)
        }
        assert aggregated == {
            reviewed.pk: (Decimal(4), Decimal(4)),
            unreviewed.pk: (None, None),
        }


def test_annotate_state_rank_follows_pending_then_state():
    event = EventFactory()
    expected = {
        SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED).pk: 1,
        SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED).pk: 2,
        SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED).pk: 3,
        SubmissionFactory(event=event, state=SubmissionStates.REJECTED).pk: 4,
        SubmissionFactory(event=event, state=SubmissionStates.WITHDRAWN).pk: 5,
        SubmissionFactory(
            event=event,
            state=SubmissionStates.SUBMITTED,
            pending_state=SubmissionStates.ACCEPTED,
        ).pk: 2,
        SubmissionFactory(
            event=event,
            state=SubmissionStates.SUBMITTED,
            pending_state=SubmissionStates.REJECTED,
        ).pk: 4,
        SubmissionFactory(
            event=event,
            state=SubmissionStates.ACCEPTED,
            pending_state=SubmissionStates.REJECTED,
        ).pk: 4,
    }

    with scope(event=event):
        assert (
            _by_pk(annotate_state_rank(event.submissions.all()), "state_rank")
            == expected
        )


def test_review_view_submissions_prefetches_speaker_submissions_visible_to_user():
    event = EventFactory()
    with scope(event=event):
        track, other_track = TrackFactory(event=event), TrackFactory(event=event)
    orga = make_orga_user(event, can_change_submissions=True)
    reviewer = make_orga_user(
        event,
        is_reviewer=True,
        can_change_submissions=False,
        can_change_organiser_settings=False,
    )
    with scope(event=event):
        reviewer.teams.first().limit_tracks.add(track)
    submission = SubmissionFactory(event=event, title="Zebra", track=track)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    ResourceFactory(submission=submission)
    visible = SubmissionFactory(event=event, title="Aardvark", track=track)
    visible.speakers.add(speaker)
    hidden = SubmissionFactory(event=event, title="Mole", track=other_track)
    hidden.speakers.add(speaker)

    with scope(event=event):
        result = review_view_submissions(event, orga).get(pk=submission.pk)
        assert list(result.speakers.first().submissions.all()) == [
            visible,
            hidden,
            submission,
        ]

        result = review_view_submissions(event, reviewer).get(pk=submission.pk)
        assert list(result.speakers.first().submissions.all()) == [visible, submission]
