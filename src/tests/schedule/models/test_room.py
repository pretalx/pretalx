# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import uuid

import pytest
from django_scopes import scope

from pretalx.schedule.models import Room
from tests.factories import (
    AvailabilityFactory,
    RoomFactory,
    ScheduleFactory,
    TalkSlotFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_room_log_parent_is_event():
    room = RoomFactory()

    assert room.log_parent == room.event


def test_room_ordering_and_visibility(event):
    hidden = RoomFactory(event=event, position=1, hidden=True)
    visible = RoomFactory(event=event, position=0)

    assert list(event.rooms.all()) == [visible, hidden]
    assert list(Room.get_order_queryset(event)) == [visible, hidden]
    assert list(event.rooms.visible()) == [visible]
    assert list(Room.objects.visible()) == [visible]


def test_room_usage_predicates(event):
    unused_room = RoomFactory(event=event)
    historic_room = RoomFactory(event=event)
    historic_schedule = ScheduleFactory(event=event, version="v0", published=None)
    TalkSlotFactory(submission=None, room=historic_room, schedule=historic_schedule)
    current_room = TalkSlotFactory(submission__event=event).room
    annotated = RoomFactory(event=event)
    annotated.has_slots = True
    annotated.has_scheduled_slots = False

    with scope(event=event):
        predicates = [
            (room.is_deletable, room.is_in_use)
            for room in (unused_room, historic_room, current_room, annotated)
        ]

    assert predicates == [(True, False), (False, False), (False, True), (False, False)]


def test_room_uuid():
    guid = uuid.uuid4()
    custom = RoomFactory(guid=guid)
    generated = RoomFactory(guid=None)
    unsaved = Room(name="Unsaved", guid=None)

    first = generated.uuid
    del generated.__dict__["uuid"]  # clear cached_property

    assert custom.uuid == guid
    assert isinstance(first, uuid.UUID)
    assert first.version == 5
    assert generated.uuid == first
    assert unsaved.uuid == ""


def test_room_slug():
    room = RoomFactory(name="Main Hall")

    assert room.slug == f"{room.id}-main-hall"


def test_room_full_availability(event):
    room = RoomFactory(event=event)

    with scope(event=event):
        empty = room.full_availability
        avail = AvailabilityFactory(event=event, room=room)
        del room.__dict__["full_availability"]
        result = room.full_availability

    assert empty == []
    assert [(a.start, a.end) for a in result] == [(avail.start, avail.end)]


def test_room_move_swaps_positions_and_stops_at_boundaries(event):
    first, second = (RoomFactory(event=event, position=i) for i in range(2))

    positions = []
    for room, up in ((first, True), (second, False), (first, False), (first, True)):
        room.move(up=up)
        first.refresh_from_db(fields=["position"])
        second.refresh_from_db(fields=["position"])
        positions.append((first.position, second.position))

    assert positions == [(0, 1), (0, 1), (1, 0), (0, 1)]
