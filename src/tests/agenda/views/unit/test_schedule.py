from types import SimpleNamespace

import pytest
from django.test import RequestFactory
from django_scopes import scope, scopes_disabled

from pretalx.agenda.views.schedule import (
    ChangelogView,
    ScheduleMixin,
    ScheduleView,
    talk_sort_key,
)
from tests.utils import make_request, make_view

pytestmark = pytest.mark.unit


class ConcreteScheduleMixin(ScheduleMixin):
    """Minimal concrete class to test ScheduleMixin in isolation."""

    def __init__(self, request, kwargs=None):
        self.request = request
        self.kwargs = kwargs or {}


@pytest.mark.django_db
def test_schedule_mixin_version_returns_none_without_kwarg(event):
    rf = RequestFactory()
    request = rf.get("/")
    request.event = event

    mixin = ConcreteScheduleMixin(request)

    assert mixin.version is None


@pytest.mark.django_db
def test_schedule_mixin_version_returns_decoded_version(event):
    rf = RequestFactory()
    request = rf.get("/")
    request.event = event

    mixin = ConcreteScheduleMixin(request, kwargs={"version": "v1%20beta"})

    assert mixin.version == "v1 beta"


@pytest.mark.django_db
def test_schedule_mixin_get_object_returns_matching_schedule(event):
    """get_object returns a schedule matching the version kwarg (case-insensitive)."""
    with scope(event=event):
        event.release_schedule("V1")

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event

    mixin = ConcreteScheduleMixin(request, kwargs={"version": "v1"})

    with scopes_disabled():
        result = mixin.get_object()

    assert result.version == "V1"


@pytest.mark.django_db
def test_schedule_mixin_get_object_falls_back_to_current_schedule(event):
    """get_object returns current_schedule when no version kwarg is given."""
    with scope(event=event):
        event.release_schedule("v1")

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event

    mixin = ConcreteScheduleMixin(request)

    with scopes_disabled():
        result = mixin.get_object()

    assert result == event.current_schedule


@pytest.mark.django_db
def test_schedule_mixin_get_object_returns_current_schedule_for_unknown_version(event):
    """get_object falls back to current_schedule for a nonexistent version."""
    with scope(event=event):
        event.release_schedule("v1")

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event

    mixin = ConcreteScheduleMixin(request, kwargs={"version": "nonexistent"})

    with scopes_disabled():
        result = mixin.get_object()

    assert result == event.current_schedule


@pytest.mark.django_db
def test_schedule_mixin_get_object_returns_none_when_no_schedules(event):
    """get_object returns None when there is no current_schedule and no version match."""
    rf = RequestFactory()
    request = rf.get("/")
    request.event = event

    mixin = ConcreteScheduleMixin(request)

    with scopes_disabled():
        result = mixin.get_object()

    assert result is None


@pytest.mark.django_db
def test_schedule_mixin_get_object_sets_event_on_schedule(event):
    """get_object sets schedule.event to request.event for cache reuse."""
    with scope(event=event):
        event.release_schedule("v1")

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event

    mixin = ConcreteScheduleMixin(request)

    with scopes_disabled():
        result = mixin.get_object()

    assert result.event is event


def test_talk_sort_key_sorts_by_start_then_title():
    """talk_sort_key sorts by start time, then by submission title."""
    slot_a = SimpleNamespace(start=1, submission=SimpleNamespace(title="Beta"))
    slot_b = SimpleNamespace(start=1, submission=SimpleNamespace(title="Alpha"))
    slot_c = SimpleNamespace(start=2, submission=SimpleNamespace(title="Alpha"))

    result = sorted([slot_a, slot_b, slot_c], key=talk_sort_key)

    assert result == [slot_b, slot_a, slot_c]


def test_talk_sort_key_handles_no_submission():
    """talk_sort_key uses empty string for title when submission is None."""
    slot = SimpleNamespace(start=1, submission=None)

    assert talk_sort_key(slot) == (1, "")


@pytest.mark.django_db
def test_schedule_view_show_talk_list_when_path_ends_with_talk(event):
    """show_talk_list returns True when request path ends with /talk/."""
    request = make_request(event, path="/myevent/talk/")
    view = make_view(ScheduleView, request)

    assert view.show_talk_list() is True


@pytest.mark.django_db
def test_schedule_view_show_talk_list_from_display_settings(event):
    """show_talk_list returns True when event display_settings schedule is 'list'."""
    event.display_settings["schedule"] = "list"
    event.save()

    request = make_request(event, path="/myevent/schedule/")
    view = make_view(ScheduleView, request)

    assert view.show_talk_list() is True


@pytest.mark.django_db
def test_schedule_view_show_talk_list_false_for_grid(event):
    """show_talk_list returns False for grid schedule not at /talk/ path."""
    event.display_settings["schedule"] = "grid"
    event.save()

    request = make_request(event, path="/myevent/schedule/")
    view = make_view(ScheduleView, request)

    assert view.show_talk_list() is False


@pytest.mark.django_db
def test_changelog_view_schedules_returns_published_only(event):
    """ChangelogView.schedules returns only schedules with a version set."""
    with scope(event=event):
        event.release_schedule("v1")
        event.release_schedule("v2")

    request = make_request(event)
    view = make_view(ChangelogView, request)

    with scopes_disabled():
        result = list(view.schedules())

    versions = {s.version for s in result}
    assert versions == {"v1", "v2"}


@pytest.mark.django_db
def test_schedule_view_get_object_returns_wip_for_wip_version(event):
    """ScheduleView.get_object returns wip_schedule when version is 'wip'."""
    request = make_request(event)
    view = make_view(ScheduleView, request, version="wip")

    with scopes_disabled():
        result = view.get_object()

    assert result == event.wip_schedule
    assert result.version is None
