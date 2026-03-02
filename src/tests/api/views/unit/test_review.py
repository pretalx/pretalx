# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.views.review import ReviewViewSet
from tests.factories import SpeakerFactory, SpeakerRoleFactory, UserFactory
from tests.utils import make_api_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_reviewviewset_visible_submissions_excludes_speaker_talks(
    event, review_user, submission
):
    """Reviewer doesn't see submissions they are a speaker on."""
    # Add review_user as a speaker on the existing submission
    speaker_profile = SpeakerFactory(event=event, user=review_user)
    submission.speakers.add(speaker_profile)
    # Create a second submission that review_user is NOT a speaker on
    other_role = SpeakerRoleFactory(submission__event=event, speaker__event=event)
    other_sub = other_role.submission

    request = make_api_request(event=event, user=review_user)
    view = make_view(ReviewViewSet, request)

    visible = list(view.visible_submissions)

    # The submission where review_user is a speaker should be excluded
    assert submission not in visible
    # The other submission should still be visible
    assert other_sub in visible


def test_reviewviewset_visible_submissions_organiser_sees_all(
    event, orga_user, submission
):
    """Organiser (non-reviewer-only) sees all submissions they're not a speaker on."""
    other_role = SpeakerRoleFactory(submission__event=event, speaker__event=event)
    other_sub = other_role.submission

    request = make_api_request(event=event, user=orga_user)
    view = make_view(ReviewViewSet, request)

    visible = list(view.visible_submissions)

    # Organiser should see both submissions (neither has orga_user as speaker)
    assert submission in visible
    assert other_sub in visible


def test_reviewviewset_visible_submissions_empty_without_event(event):
    """Returns empty queryset when event is None."""
    user = UserFactory()
    request = make_api_request(user=user)
    # No event set on the request, so view.event will be None
    view = make_view(ReviewViewSet, request)

    visible = list(view.visible_submissions)

    assert visible == []


def test_reviewviewset_get_queryset_empty_for_anonymous(event):
    """Anonymous user gets empty queryset."""
    request = make_api_request(event=event)
    # make_api_request without user leaves request.user as AnonymousUser
    view = make_view(ReviewViewSet, request)

    result = list(view.get_queryset())

    assert result == []


def test_reviewviewset_get_queryset_empty_without_event():
    """get_queryset returns empty queryset when event is None."""
    user = UserFactory()
    request = make_api_request(user=user)
    view = make_view(ReviewViewSet, request)

    result = list(view.get_queryset())

    assert result == []
