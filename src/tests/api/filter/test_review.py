# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.test import RequestFactory

from pretalx.api.filters.review import ReviewFilter
from pretalx.submission.models import Review, SubmissionStates
from tests.factories import (
    EventFactory,
    ReviewFactory,
    SpeakerRoleFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TeamFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

rf = RequestFactory()


def test_review_filter_init_without_event_uses_empty_querysets():
    request = rf.get("/")
    f = ReviewFilter(request=request)

    assert f.filters["submission"].queryset.count() == 0
    assert f.filters["user"].queryset.count() == 0


def test_review_filter_init_with_event_populates_querysets():
    event = EventFactory()
    role = SpeakerRoleFactory(submission__event=event, speaker__event=event)
    sub = role.submission
    speaker = role.speaker
    track = TrackFactory(event=event)
    SubmissionTypeFactory(event=event)
    reviewer = UserFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(reviewer)

    request = rf.get("/")
    request.event = event
    f = ReviewFilter(request=request)
    expected_stypes = set(event.submission_types.all())

    assert list(f.filters["submission"].queryset) == [sub]
    assert list(f.filters["user"].queryset) == [reviewer]
    assert list(f.filters["speaker"].queryset) == [speaker]
    assert list(f.filters["submission__track"].queryset) == [track]
    assert set(f.filters["submission__submission_type"].queryset) == expected_stypes


def test_review_filter_filters_by_submission_code(event):
    sub1 = SubmissionFactory(event=event)
    sub2 = SubmissionFactory(event=event)
    review1 = ReviewFactory(submission=sub1)
    ReviewFactory(submission=sub2)

    request = rf.get("/")
    request.event = event
    fs = ReviewFilter(
        data={"submission": sub1.code}, queryset=Review.objects.all(), request=request
    )

    assert list(fs.qs) == [review1]


def test_review_filter_filters_by_submission_state(event):
    sub_submitted = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
    sub_accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    review1 = ReviewFactory(submission=sub_submitted)
    ReviewFactory(submission=sub_accepted)

    request = rf.get("/")
    request.event = event
    fs = ReviewFilter(
        data={"submission__state": [SubmissionStates.SUBMITTED]},
        queryset=Review.objects.all(),
        request=request,
    )

    assert list(fs.qs) == [review1]


def test_review_filter_filters_by_track(event):
    track = TrackFactory(event=event)
    sub_with_track = SubmissionFactory(event=event, track=track)
    sub_without = SubmissionFactory(event=event)
    review1 = ReviewFactory(submission=sub_with_track)
    ReviewFactory(submission=sub_without)

    request = rf.get("/")
    request.event = event
    fs = ReviewFilter(
        data={"submission__track": str(track.pk)},
        queryset=Review.objects.all(),
        request=request,
    )

    assert list(fs.qs) == [review1]


def test_review_filter_filters_by_reviewer(event):
    user1 = UserFactory()
    user2 = UserFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True, is_reviewer=True)
    team.members.add(user1, user2)

    sub = SubmissionFactory(event=event)
    review1 = ReviewFactory(submission=sub, user=user1)
    ReviewFactory(submission=sub, user=user2)

    request = rf.get("/")
    request.event = event
    fs = ReviewFilter(
        data={"user": user1.code}, queryset=Review.objects.all(), request=request
    )

    assert list(fs.qs) == [review1]


def test_review_filter_filters_by_speaker(event):
    role1 = SpeakerRoleFactory(submission__event=event, speaker__event=event)
    role2 = SpeakerRoleFactory(submission__event=event, speaker__event=event)
    speaker1 = role1.speaker
    sub1 = role1.submission
    sub2 = role2.submission
    review1 = ReviewFactory(submission=sub1)
    ReviewFactory(submission=sub2)

    request = rf.get("/")
    request.event = event
    fs = ReviewFilter(
        data={"speaker": speaker1.code}, queryset=Review.objects.all(), request=request
    )

    assert list(fs.qs) == [review1]
