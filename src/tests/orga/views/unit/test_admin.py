# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.test import override_settings

from pretalx.orga.views.admin import AdminDashboard, AdminUserView
from tests.factories import (
    ActivityLogFactory,
    EventFactory,
    SpeakerFactory,
    SubmissionFactory,
    UserFactory,
)
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


@pytest.mark.parametrize(
    ("action", "query", "expected"),
    (
        ("list", "", set()),
        ("list", "ab", set()),
        ("list", "Searchable", {("Searchable Name", 2)}),
        ("list", "findme@example", {("Find Me", 0)}),
        ("detail", "", {("Searchable Name", 2), ("Find Me", 0), ("Admin", 0)}),
    ),
    ids=("empty-search", "short-search", "by-name", "by-email", "detail"),
)
def test_admin_user_view_get_queryset(action, query, expected):
    event = EventFactory()
    speaker = SpeakerFactory(user__name="Searchable Name", event=event)
    for _ in range(2):
        SubmissionFactory(event=event).speakers.add(speaker)
    UserFactory(name="Find Me", email="findme@example.com")
    admin_user = UserFactory(name="Admin", is_administrator=True)
    request = make_request(event, user=admin_user)
    request.GET = {"q": query} if query else {}
    view = make_view(AdminUserView, request)
    view.action = action

    qs = view.get_queryset()

    assert {(user.name, user.submission_count) for user in qs} == expected


def _admin_user_detail_view(target):
    admin_user = UserFactory(is_administrator=True)
    request = make_request(None, user=admin_user)
    view = make_view(AdminUserView, request)
    view.action = "detail"
    view.object = target
    view.url_name = "admin.user"
    view.namespace = "orga"
    return view


def test_admin_user_view_history_shows_actions_by_the_user():
    target = UserFactory()
    other = UserFactory()
    event = EventFactory()
    logs = [
        ActivityLogFactory(event=event, person=target, content_object=event)
        for _ in range(11)
    ]
    ActivityLogFactory(event=event, person=other, content_object=event)

    view = _admin_user_detail_view(target)

    assert set(view.history_log_entries) == set(logs)
    assert set(view.history_tablist) == {"history"}
    context = view.get_context_data()
    assert context["history_with_objects"] is True
    assert context["history_show_event"] is True


def test_admin_user_view_history_hidden_without_actions():
    view = _admin_user_detail_view(UserFactory())

    assert view.history_log_entries == []
    assert view.history_tablist == {}
    assert set(view.get_context_data()["tablist"]) == {"teams", "submissions"}
