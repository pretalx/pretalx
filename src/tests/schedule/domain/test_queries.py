# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils.timezone import now

from pretalx.schedule.domain.queries.schedule import (
    parallel_slots,
    published_schedules,
    room_neighbour_slots,
    schedule_day_start,
)
from tests.factories import (
    RoomFactory,
    ScheduleFactory,
    SubmissionFactory,
    TalkSlotFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def make_slot(event, room, *, hours, duration=1, is_visible=True):
    start = event.datetime_from + dt.timedelta(hours=hours)
    return TalkSlotFactory(
        submission=SubmissionFactory(event=event),
        room=room,
        start=start,
        end=start + dt.timedelta(hours=duration),
        is_visible=is_visible,
    )


def test_published_schedules_excludes_wip(event):
    assert list(published_schedules(event)) == []


def test_published_schedules_includes_only_versioned(event):
    ScheduleFactory(event=event, version="v1")

    result = list(published_schedules(event))

    assert [s.version for s in result] == ["v1"]


def test_published_schedules_orders_newest_first(event):
    ScheduleFactory(event=event, version="v1", published=now() - dt.timedelta(hours=2))
    ScheduleFactory(event=event, version="v2", published=now() - dt.timedelta(hours=1))

    result = list(published_schedules(event))

    assert [s.version for s in result] == ["v2", "v1"]


def test_published_schedules_preloads_event(event, django_assert_num_queries):
    ScheduleFactory(event=event, version="v1")

    result = list(published_schedules(event))

    with django_assert_num_queries(0):
        _ = result[0].event.slug


@pytest.mark.parametrize(
    ("hours", "expected_offset"), ((10, 4), (3, -20)), ids=["daytime", "after_midnight"]
)
def test_schedule_day_start_uses_four_am_boundary(event, hours, expected_offset):
    room = RoomFactory(event=event)
    slot = make_slot(event, room, hours=hours)

    assert schedule_day_start(slot) == event.datetime_from + dt.timedelta(
        hours=expected_offset
    )


def test_room_neighbour_slots_returns_adjacent_slots_in_room(event):
    room = RoomFactory(event=event)
    earliest = make_slot(event, room, hours=9)
    previous = make_slot(event, room, hours=11)
    slot = make_slot(event, room, hours=13)
    next_slot = make_slot(event, room, hours=15)
    make_slot(event, room, hours=17)

    neighbours = room_neighbour_slots(slot)

    assert neighbours == {"previous": previous, "next": next_slot}
    assert earliest not in neighbours.values()


@pytest.mark.parametrize(
    ("neighbour_hours", "same_room", "is_visible"),
    (((11, 15), False, True), ((-2, 34), True, True), ((11, 15), True, False)),
    ids=["other_room", "other_schedule_day", "invisible"],
)
def test_room_neighbour_slots_ignores_unrelated_slots(
    event, neighbour_hours, same_room, is_visible
):
    room = RoomFactory(event=event)
    neighbour_room = room if same_room else RoomFactory(event=event)
    for hours in neighbour_hours:
        make_slot(event, neighbour_room, hours=hours, is_visible=is_visible)
    slot = make_slot(event, room, hours=13)

    assert room_neighbour_slots(slot) == {"previous": None, "next": None}


@pytest.mark.parametrize(
    ("other_hours", "is_visible", "expected"),
    ((13, True, 1), (13.5, True, 1), (14, True, 0), (12, True, 0), (13, False, 0)),
    ids=["identical", "overlapping", "directly_after", "directly_before", "invisible"],
)
def test_parallel_slots_returns_overlaps_only(event, other_hours, is_visible, expected):
    room = RoomFactory(event=event)
    slot = make_slot(event, room, hours=13)
    other = make_slot(
        event, RoomFactory(event=event), hours=other_hours, is_visible=is_visible
    )

    assert list(parallel_slots(slot)) == ([other] if expected else [])


def test_parallel_slots_ignores_further_slots_of_same_submission(event):
    room = RoomFactory(event=event)
    slot = make_slot(event, room, hours=13)
    TalkSlotFactory(
        submission=slot.submission,
        room=RoomFactory(event=event),
        start=slot.start,
        end=slot.end,
        is_visible=True,
    )

    assert list(parallel_slots(slot)) == []
