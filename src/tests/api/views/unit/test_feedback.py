# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.views.feedback import FeedbackViewSet
from tests.factories import FeedbackFactory
from tests.utils import make_api_request, make_orga_user, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_feedback_viewset_get_queryset_returns_event_feedback_to_orga_only():
    feedback = FeedbackFactory()
    event = feedback.talk.event
    FeedbackFactory()
    user = make_orga_user(event, can_change_submissions=True)

    anonymous_view = make_view(FeedbackViewSet, make_api_request(event=event))
    orga_view = make_view(FeedbackViewSet, make_api_request(event=event, user=user))

    assert list(anonymous_view.get_queryset()) == []
    assert list(orga_view.get_queryset()) == [feedback]
