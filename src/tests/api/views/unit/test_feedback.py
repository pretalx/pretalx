# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.views.feedback import FeedbackViewSet
from tests.factories import FeedbackFactory
from tests.utils import make_api_request, make_orga_user, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_feedback_viewset_get_queryset_anonymous_returns_empty():
    feedback = FeedbackFactory()
    request = make_api_request(event=feedback.talk.event)
    view = make_view(FeedbackViewSet, request)
    view.action = "list"

    qs = list(view.get_queryset())

    assert qs == []


@pytest.mark.django_db
def test_feedback_viewset_get_queryset_authenticated_returns_event_feedback():
    feedback = FeedbackFactory()
    event = feedback.talk.event
    other_feedback = FeedbackFactory()
    user = make_orga_user(event, can_change_submissions=True)
    request = make_api_request(event=event, user=user)
    view = make_view(FeedbackViewSet, request)
    view.action = "list"

    qs = list(view.get_queryset())

    assert qs == [feedback]
    assert other_feedback not in qs
