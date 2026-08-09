# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.test import override_settings

from pretalx.orga.views.admin import AdminDashboard, AdminUserView
from tests.factories import EventFactory, SpeakerFactory, SubmissionFactory, UserFactory
from tests.utils import make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_admin_dashboard_queue_length_eager_returns_none(event):
    admin_user = UserFactory(is_administrator=True)
    request = make_request(event, user=admin_user)
    view = make_view(AdminDashboard, request)

    assert view.queue_length() is None


@pytest.mark.slow
@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
def test_admin_dashboard_queue_length_broker_error_returns_string(event):
    admin_user = UserFactory(is_administrator=True)
    request = make_request(event, user=admin_user)
    view = make_view(AdminDashboard, request)

    result = view.queue_length()

    assert isinstance(result, str)


@pytest.mark.parametrize("search", ("", "ab"))
def test_admin_user_view_get_queryset_list_insufficient_search(search):
    admin_user = UserFactory(is_administrator=True)
    event = EventFactory()
    request = make_request(event, user=admin_user)
    request.GET = {"q": search} if search else {}
    view = make_view(AdminUserView, request)
    view.action = "list"

    qs = view.get_queryset()

    assert qs.count() == 0


def test_admin_user_view_get_queryset_list_with_search():
    target_user = UserFactory(name="Searchable Name")
    UserFactory(name="Other Person")
    admin_user = UserFactory(is_administrator=True)
    event = EventFactory()
    request = make_request(event, user=admin_user)
    request.GET = {"q": "Searchable"}
    view = make_view(AdminUserView, request)
    view.action = "list"

    qs = view.get_queryset()

    assert list(qs) == [target_user]


def test_admin_user_view_get_queryset_list_search_by_email():
    target_user = UserFactory(email="findme@example.com")
    UserFactory(email="other@example.com")
    admin_user = UserFactory(is_administrator=True)
    event = EventFactory()
    request = make_request(event, user=admin_user)
    request.GET = {"q": "findme@example"}
    view = make_view(AdminUserView, request)
    view.action = "list"

    qs = view.get_queryset()

    assert list(qs) == [target_user]


def test_admin_user_view_get_queryset_detail_returns_all():
    user1 = UserFactory()
    user2 = UserFactory()
    admin_user = UserFactory(is_administrator=True)
    event = EventFactory()
    request = make_request(event, user=admin_user)
    request.GET = {}
    view = make_view(AdminUserView, request)
    view.action = "detail"

    qs = view.get_queryset()

    assert set(qs) == {user1, user2, admin_user}


def test_admin_user_view_get_queryset_annotates_submission_count():
    user = UserFactory()
    event = EventFactory()
    speaker = SpeakerFactory(user=user, event=event)
    sub1 = SubmissionFactory(event=event)
    sub2 = SubmissionFactory(event=event)
    sub1.speakers.add(speaker)
    sub2.speakers.add(speaker)

    admin_user = UserFactory(is_administrator=True)
    request = make_request(event, user=admin_user)
    request.GET = {"q": user.name}
    view = make_view(AdminUserView, request)
    view.action = "list"

    result = list(view.get_queryset())

    assert len(result) == 1
    assert result[0].submission_count == 2
