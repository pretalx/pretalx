# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.filters.submission import SubmissionFilter
from pretalx.submission.models import Submission, SubmissionStates
from tests.factories import SubmissionFactory, TrackFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    "states",
    (
        [SubmissionStates.SUBMITTED],
        [SubmissionStates.SUBMITTED, SubmissionStates.ACCEPTED],
    ),
    ids=["single", "multiple"],
)
def test_submission_filter_filters_by_state(event, states):
    for state in (
        SubmissionStates.SUBMITTED,
        SubmissionStates.ACCEPTED,
        SubmissionStates.REJECTED,
    ):
        SubmissionFactory(event=event, state=state)

    fs = SubmissionFilter(data={"state": states}, queryset=event.submissions.all())

    assert sorted(sub.state for sub in fs.qs) == sorted(states)


def test_submission_filter_filters_by_track(event):
    track = TrackFactory(event=event)
    sub_with_track = SubmissionFactory(event=event, track=track)
    SubmissionFactory(event=event)

    fs = SubmissionFilter(
        data={"track": str(track.pk)}, queryset=event.submissions.all()
    )

    assert list(fs.qs) == [sub_with_track]


def test_submission_filter_filters_by_is_featured(event):
    sub_featured = SubmissionFactory(event=event, is_featured=True)
    SubmissionFactory(event=event, is_featured=False)

    fs = SubmissionFilter(
        data={"is_featured": "true"}, queryset=event.submissions.all()
    )

    assert list(fs.qs) == [sub_featured]


def test_submission_filter_filters_by_submission_type(event):
    sub = SubmissionFactory(event=event)
    other_event_sub = SubmissionFactory()

    fs = SubmissionFilter(
        data={"submission_type": str(sub.submission_type.pk)},
        queryset=Submission.objects.filter(pk__in=[sub.pk, other_event_sub.pk]),
    )

    assert list(fs.qs) == [sub]
