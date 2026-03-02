# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from types import SimpleNamespace

import pytest
from django.test import RequestFactory
from django_scopes import scope

from pretalx.agenda.views.schedule import (
    ChangelogView,
    ScheduleMixin,
    ScheduleView,
    talk_sort_key,
)
from tests.utils import make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


class ConcreteScheduleMixin(ScheduleMixin):
    """Minimal concrete class to test ScheduleMixin in isolation."""

    def __init__(self, request, kwargs=None):
        self.request = request
        self.kwargs = kwargs or {}


def test_schedule_mixin_version_returns_decoded_version(event):
    rf = RequestFactory()
    request = rf.get("/")
    request.event = event

    mixin = ConcreteScheduleMixin(request, kwargs={"version": "v1%20beta"})

    assert mixin.version == "v1 beta"


def test_schedule_mixin_get_object_returns_matching_schedule(event):
    with scope(event=event):
        event.release_schedule("V1")

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event

    mixin = ConcreteScheduleMixin(request, kwargs={"version": "v1"})

    result = mixin.get_object()

    assert result.version == "V1"


def test_schedule_mixin_get_object_falls_back_to_current_schedule(event):
    with scope(event=event):
        event.release_schedule("v1")

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event

    mixin = ConcreteScheduleMixin(request)

    result = mixin.get_object()

    assert result == event.current_schedule


def test_schedule_mixin_get_object_returns_current_schedule_for_unknown_version(event):
    with scope(event=event):
        event.release_schedule("v1")

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event

    mixin = ConcreteScheduleMixin(request, kwargs={"version": "nonexistent"})

    result = mixin.get_object()

    assert result == event.current_schedule


def test_schedule_mixin_get_object_returns_none_when_no_schedules(event):
    rf = RequestFactory()
    request = rf.get("/")
    request.event = event

    mixin = ConcreteScheduleMixin(request)

    result = mixin.get_object()

    assert result is None


def test_schedule_mixin_get_object_sets_event_on_schedule(event):
    with scope(event=event):
        event.release_schedule("v1")

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event

    mixin = ConcreteScheduleMixin(request)

    result = mixin.get_object()

    assert result.event is event


def test_talk_sort_key_sorts_by_start_then_title():
    slot_a = SimpleNamespace(start=1, submission=SimpleNamespace(title="Beta"))
    slot_b = SimpleNamespace(start=1, submission=SimpleNamespace(title="Alpha"))
    slot_c = SimpleNamespace(start=2, submission=SimpleNamespace(title="Alpha"))

    result = sorted([slot_a, slot_b, slot_c], key=talk_sort_key)

    assert result == [slot_b, slot_a, slot_c]


def test_talk_sort_key_handles_no_submission():
    slot = SimpleNamespace(start=1, submission=None)

    assert talk_sort_key(slot) == (1, "")


def test_schedule_view_show_talk_list_when_path_ends_with_talk(event):
    request = make_request(event, path="/myevent/talk/")
    view = make_view(ScheduleView, request)

    assert view.show_talk_list() is True


def test_schedule_view_show_talk_list_from_display_settings(event):
    event.display_settings["schedule"] = "list"

    request = make_request(event, path="/myevent/schedule/")
    view = make_view(ScheduleView, request)

    assert view.show_talk_list() is True


def test_schedule_view_show_talk_list_false_for_grid(event):
    event.display_settings["schedule"] = "grid"

    request = make_request(event, path="/myevent/schedule/")
    view = make_view(ScheduleView, request)

    assert view.show_talk_list() is False


def test_changelog_view_schedules_returns_published_only(event):
    with scope(event=event):
        event.release_schedule("v1")
        event.release_schedule("v2")

    request = make_request(event)
    view = make_view(ChangelogView, request)

    result = list(view.schedules())

    versions = {s.version for s in result}
    assert versions == {"v1", "v2"}


def test_schedule_view_get_object_returns_wip_for_wip_version(event):
    request = make_request(event)
    view = make_view(ScheduleView, request, version="wip")

    result = view.get_object()

    assert result == event.wip_schedule
    assert result.version is None
