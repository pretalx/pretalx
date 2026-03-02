# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from pretalx.api.filters.feedback import FeedbackFilter
from pretalx.submission.models import Feedback
from tests.factories import (
    EventFactory,
    FeedbackFactory,
    SubmissionFactory,
    TeamFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

rf = RequestFactory()


def test_feedback_filter_init_with_orga_populates_queryset():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    user = UserFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True)
    team.members.add(user)

    request = rf.get("/")
    request.event = event
    request.user = user
    f = FeedbackFilter(request=request)

    assert list(f.filters["submission"].queryset) == [sub]


def test_feedback_filter_init_anonymous_user_without_schedule():
    event = EventFactory()
    SubmissionFactory(event=event)

    request = rf.get("/")
    request.event = event
    request.user = AnonymousUser()
    f = FeedbackFilter(request=request)

    assert f.filters["submission"].queryset.count() == 0


def test_feedback_filter_filters_by_submission_code(event):
    sub1 = SubmissionFactory(event=event)
    sub2 = SubmissionFactory(event=event)
    fb1 = FeedbackFactory(talk=sub1)
    FeedbackFactory(talk=sub2)

    user = UserFactory()
    team = TeamFactory(organiser=event.organiser, all_events=True)
    team.members.add(user)

    request = rf.get("/")
    request.event = event
    request.user = user
    fs = FeedbackFilter(
        data={"submission": sub1.code}, queryset=Feedback.objects.all(), request=request
    )

    assert list(fs.qs) == [fb1]
