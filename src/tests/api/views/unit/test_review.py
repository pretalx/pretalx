# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.views.review import ReviewViewSet
from tests.factories import SpeakerFactory, UserFactory
from tests.utils import make_api_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_reviewviewset_visible_submissions_excludes_own_talks_for_reviewer(
    event, review_user, orga_user, submission, other_submission
):
    speaker_profile = SpeakerFactory(event=event, user=review_user)
    submission.speakers.add(speaker_profile)

    reviewer_view = make_view(
        ReviewViewSet, make_api_request(event=event, user=review_user)
    )
    orga_view = make_view(ReviewViewSet, make_api_request(event=event, user=orga_user))

    assert list(reviewer_view.visible_submissions) == [other_submission]
    assert set(orga_view.visible_submissions) == {submission, other_submission}


def test_reviewviewset_empty_without_event_or_user(event):
    no_event_view = make_view(ReviewViewSet, make_api_request(user=UserFactory()))
    anonymous_view = make_view(ReviewViewSet, make_api_request(event=event))

    assert list(no_event_view.visible_submissions) == []
    assert list(no_event_view.get_queryset()) == []
    assert list(anonymous_view.get_queryset()) == []
