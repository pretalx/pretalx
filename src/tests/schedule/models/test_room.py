import uuid

import pytest
from django_scopes import scope, scopes_disabled

from pretalx.schedule.models import Room
from tests.factories import AvailabilityFactory, RoomFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_room_basic_properties():
    room = RoomFactory(name="Main Hall")

    assert str(room) == "Main Hall"
    assert room.log_prefix == "pretalx.room"
    assert room.log_parent == room.event


@pytest.mark.django_db
def test_room_get_order_queryset(event):
    room2 = RoomFactory(event=event, position=1)
    room1 = RoomFactory(event=event, position=0)

    with scopes_disabled():
        result = list(Room.get_order_queryset(event))

    assert result == [room1, room2]


@pytest.mark.django_db
def test_room_uuid_with_guid():
    """When a GUID is set, uuid returns it directly."""
    guid = uuid.uuid4()
    room = RoomFactory(guid=guid)

    assert room.uuid == guid


@pytest.mark.django_db
def test_room_uuid_without_guid():
    """Without a GUID, uuid is computed from pk and instance identifier."""
    room = RoomFactory(guid=None)

    result = room.uuid

    assert isinstance(result, uuid.UUID)
    assert result.version == 5


@pytest.mark.django_db
def test_room_uuid_without_pk():
    """Without a pk, uuid returns empty string."""
    room = Room(name="Unsaved", guid=None)

    assert room.uuid == ""


@pytest.mark.django_db
def test_room_uuid_is_stable():
    """The same room always produces the same UUID."""
    room = RoomFactory(guid=None)

    uuid1 = room.uuid
    del room.__dict__["uuid"]  # clear cached_property
    uuid2 = room.uuid

    assert uuid1 == uuid2


@pytest.mark.django_db
def test_room_slug():
    room = RoomFactory(name="Main Hall")

    assert room.slug == f"{room.id}-main-hall"


@pytest.mark.django_db
def test_room_full_availability_empty(event):
    room = RoomFactory(event=event)

    with scope(event=event):
        result = room.full_availability

    assert result == []


@pytest.mark.django_db
def test_room_full_availability_with_data(event):
    room = RoomFactory(event=event)
    avail = AvailabilityFactory(event=event, room=room)

    with scope(event=event):
        result = room.full_availability

    assert len(result) == 1
    assert result[0].start == avail.start
    assert result[0].end == avail.end


@pytest.mark.django_db
def test_room_ordering_by_position(event):
    room_b = RoomFactory(event=event, position=2)
    room_a = RoomFactory(event=event, position=1)

    with scopes_disabled():
        rooms = list(event.rooms.all())

    assert rooms == [room_a, room_b]


@pytest.mark.parametrize(
    ("move_index", "up"), ((0, False), (1, True)), ids=["down", "up"]
)
@pytest.mark.django_db
def test_room_move_swaps_positions(event, move_index, up):
    rooms = [RoomFactory(event=event, position=i) for i in range(2)]

    with scopes_disabled():
        rooms[move_index].move(up=up)

    for room in rooms:
        room.refresh_from_db()
    assert rooms[0].position == 1
    assert rooms[1].position == 0


@pytest.mark.parametrize(
    ("move_index", "up"), ((0, True), (1, False)), ids=["up_at_top", "down_at_bottom"]
)
@pytest.mark.django_db
def test_room_move_noop_at_boundary(event, move_index, up):
    rooms = [RoomFactory(event=event, position=i) for i in range(2)]

    with scopes_disabled():
        rooms[move_index].move(up=up)

    for room in rooms:
        room.refresh_from_db()
    assert rooms[0].position == 0
    assert rooms[1].position == 1
