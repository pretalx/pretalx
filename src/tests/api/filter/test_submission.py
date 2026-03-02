# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.filters.submission import SubmissionFilter
from pretalx.submission.models import Submission, SubmissionStates
from tests.factories import SubmissionFactory, TrackFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_submission_filter_filters_by_state(event):
    sub_submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

    fs = SubmissionFilter(
        data={"state": [SubmissionStates.SUBMITTED]}, queryset=event.submissions.all()
    )

    assert list(fs.qs) == [sub_submitted]


def test_submission_filter_filters_by_multiple_states(event):
    sub1 = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    sub2 = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    SubmissionFactory(event=event, state=SubmissionStates.REJECTED)

    fs = SubmissionFilter(
        data={"state": [SubmissionStates.SUBMITTED, SubmissionStates.ACCEPTED]},
        queryset=event.submissions.all(),
    )

    assert set(fs.qs) == {sub1, sub2}


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
