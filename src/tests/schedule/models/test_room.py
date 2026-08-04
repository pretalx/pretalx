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


def test_room_basic_properties():
    room = RoomFactory(name="Main Hall")

    assert str(room) == "Main Hall"
    assert room.log_prefix == "pretalx.room"
    assert room.log_parent == room.event


def test_room_get_order_queryset_includes_hidden_rooms(event):
    room2 = RoomFactory(event=event, position=1, hidden=True)
    room1 = RoomFactory(event=event, position=0)

    result = list(Room.get_order_queryset(event))

    assert result == [room1, room2]


def test_room_visible_excludes_hidden_rooms(event):
    visible = RoomFactory(event=event, position=0)
    RoomFactory(event=event, position=1, hidden=True)

    assert list(event.rooms.visible()) == [visible]
    assert list(Room.objects.visible()) == [visible]


def test_room_is_deletable_without_annotation(event):
    unused_room = RoomFactory(event=event)
    used_room = TalkSlotFactory(submission__event=event).room

    with scope(event=event):
        assert unused_room.is_deletable is True
        assert used_room.is_deletable is False


def test_room_is_in_use_without_annotation(event):
    historic_room = RoomFactory(event=event)
    historic_schedule = ScheduleFactory(event=event, version="v0", published=None)
    TalkSlotFactory(submission=None, room=historic_room, schedule=historic_schedule)
    current_room = TalkSlotFactory(submission__event=event).room

    with scope(event=event):
        assert historic_room.is_in_use is False
        assert current_room.is_in_use is True


def test_room_predicates_prefer_annotated_values(event):
    room = RoomFactory(event=event)
    room.has_slots = True
    room.has_scheduled_slots = False

    assert room.is_deletable is False
    assert room.is_in_use is False


def test_room_uuid_with_guid():
    guid = uuid.uuid4()
    room = RoomFactory(guid=guid)

    assert room.uuid == guid


def test_room_uuid_without_guid():
    room = RoomFactory(guid=None)

    result = room.uuid

    assert isinstance(result, uuid.UUID)
    assert result.version == 5


def test_room_uuid_without_pk():
    room = Room(name="Unsaved", guid=None)

    assert room.uuid == ""


def test_room_uuid_is_stable():
    room = RoomFactory(guid=None)

    uuid1 = room.uuid
    del room.__dict__["uuid"]  # clear cached_property
    uuid2 = room.uuid

    assert uuid1 == uuid2


def test_room_slug():
    room = RoomFactory(name="Main Hall")

    assert room.slug == f"{room.id}-main-hall"


def test_room_full_availability_empty(event):
    room = RoomFactory(event=event)

    with scope(event=event):
        result = room.full_availability

    assert result == []


def test_room_full_availability_with_data(event):
    room = RoomFactory(event=event)
    avail = AvailabilityFactory(event=event, room=room)

    with scope(event=event):
        result = room.full_availability

    assert len(result) == 1
    assert result[0].start == avail.start
    assert result[0].end == avail.end


def test_room_ordering_by_position(event):
    room_b = RoomFactory(event=event, position=2)
    room_a = RoomFactory(event=event, position=1)

    rooms = list(event.rooms.all())

    assert rooms == [room_a, room_b]


@pytest.mark.parametrize(
    ("move_index", "up"), ((0, False), (1, True)), ids=["down", "up"]
)
def test_room_move_swaps_positions(event, move_index, up):
    rooms = [RoomFactory(event=event, position=i) for i in range(2)]

    rooms[move_index].move(up=up)

    for room in rooms:
        room.refresh_from_db()
    assert rooms[0].position == 1
    assert rooms[1].position == 0


@pytest.mark.parametrize(
    ("move_index", "up"), ((0, True), (1, False)), ids=["up_at_top", "down_at_bottom"]
)
def test_room_move_noop_at_boundary(event, move_index, up):
    rooms = [RoomFactory(event=event, position=i) for i in range(2)]

    rooms[move_index].move(up=up)

    for room in rooms:
        room.refresh_from_db()
    assert rooms[0].position == 0
    assert rooms[1].position == 1
