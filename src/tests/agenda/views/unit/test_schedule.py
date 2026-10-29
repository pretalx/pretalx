# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from types import SimpleNamespace

import pytest
from django_scopes import scope

from pretalx.agenda.views.schedule import (
    ChangelogView,
    ScheduleMixin,
    ScheduleView,
    talk_sort_key,
)
from pretalx.schedule.domain.release import freeze_schedule
from tests.utils import make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


class ConcreteScheduleMixin(ScheduleMixin):
    def __init__(self, request, kwargs=None):
        self.request = request
        self.kwargs = kwargs or {}


def test_schedule_mixin_version_returns_url_kwarg_verbatim(event):
    mixin = ConcreteScheduleMixin(make_request(event), kwargs={"version": "v1%20beta"})

    assert mixin.version == "v1%20beta"


@pytest.mark.parametrize(
    "kwargs",
    ({"version": "v1"}, {}, {"version": "nonexistent"}),
    ids=["case_insensitive_match", "no_version", "unknown_version"],
)
def test_schedule_mixin_get_object_resolves_to_current_schedule(event, kwargs):
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "V1")

    mixin = ConcreteScheduleMixin(make_request(event), kwargs=kwargs)

    result = mixin.get_object()

    assert result == event.current_schedule
    assert result.version == "V1"
    assert result.event is event


def test_schedule_mixin_get_object_returns_none_when_no_schedules(event):
    mixin = ConcreteScheduleMixin(make_request(event))

    assert mixin.get_object() is None


def test_talk_sort_key_sorts_by_start_then_room_position():
    slot_a = SimpleNamespace(start=1, room=SimpleNamespace(position=2, id=10))
    slot_b = SimpleNamespace(start=1, room=SimpleNamespace(position=1, id=11))
    slot_c = SimpleNamespace(start=2, room=SimpleNamespace(position=1, id=12))

    result = sorted([slot_a, slot_b, slot_c], key=talk_sort_key)

    assert result == [slot_b, slot_a, slot_c]


def test_talk_sort_key_falls_back_to_room_id_when_position_missing():
    slot = SimpleNamespace(start=1, room=SimpleNamespace(position=None, id=42))

    assert talk_sort_key(slot) == (1, 42)


@pytest.mark.parametrize(
    ("path", "display_setting", "expected"),
    (
        ("/myevent/talk/", "grid", True),
        ("/myevent/schedule/", "list", True),
        ("/myevent/schedule/", "grid", False),
    ),
    ids=["talk_path", "list_setting", "grid_setting"],
)
def test_schedule_view_show_talk_list(event, path, display_setting, expected):
    event.display_settings["schedule"] = display_setting

    request = make_request(event, path=path)
    view = make_view(ScheduleView, request)

    assert view.show_talk_list() is expected


def test_changelog_view_schedules_returns_published_only(event):
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1")
        freeze_schedule(event.wip_schedule, "v2")

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
