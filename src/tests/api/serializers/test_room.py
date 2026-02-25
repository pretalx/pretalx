import datetime as dt
import uuid

import pytest
from django_scopes import scopes_disabled

from pretalx.api.serializers.room import RoomOrgaSerializer, RoomSerializer
from pretalx.common.models.settings import GlobalSettings
from tests.factories import AvailabilityFactory, EventFactory, RoomFactory
from tests.utils import make_api_request

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_room_serializer_fields():
    with scopes_disabled():
        room = RoomFactory()
    request = make_api_request(room.event)

    serializer = RoomSerializer(room, context={"request": request})
    data = serializer.data

    assert set(data.keys()) == {
        "id",
        "name",
        "description",
        "uuid",
        "guid",
        "capacity",
        "position",
    }
    assert data["id"] == room.pk
    assert data["guid"] is None
    assert data["capacity"] is None


@pytest.mark.django_db
def test_room_serializer_uuid_without_guid():
    """When no guid is set, uuid is a computed stable UUID5."""
    with scopes_disabled():
        room = RoomFactory()
    request = make_api_request(room.event)

    serializer = RoomSerializer(room, context={"request": request})

    expected = str(
        uuid.uuid5(GlobalSettings().get_instance_identifier(), f"room:{room.pk}")
    )
    assert serializer.data["uuid"] == expected


@pytest.mark.django_db
def test_room_serializer_uuid_equals_guid_when_set():
    """When a guid is set, the uuid field returns the same value."""
    guid = uuid.uuid4()
    with scopes_disabled():
        room = RoomFactory(guid=guid)
    request = make_api_request(room.event)

    serializer = RoomSerializer(room, context={"request": request})

    assert serializer.data["uuid"] == str(guid)
    assert serializer.data["guid"] == str(guid)


@pytest.mark.django_db
def test_room_serializer_uuid_is_read_only():
    request = make_api_request(EventFactory())

    serializer = RoomSerializer(context={"request": request})

    assert serializer.fields["uuid"].read_only is True


@pytest.mark.django_db
def test_room_orga_serializer_fields():
    with scopes_disabled():
        room = RoomFactory()
    request = make_api_request(room.event)

    serializer = RoomOrgaSerializer(room, context={"request": request})
    with scopes_disabled():
        data = serializer.data

    assert set(data.keys()) == {
        "id",
        "name",
        "description",
        "uuid",
        "guid",
        "capacity",
        "position",
        "speaker_info",
        "availabilities",
    }


@pytest.mark.django_db
def test_room_orga_serializer_includes_availabilities():
    with scopes_disabled():
        room = RoomFactory()
        avail = AvailabilityFactory(event=room.event, room=room)
    request = make_api_request(room.event)

    serializer = RoomOrgaSerializer(room, context={"request": request})
    with scopes_disabled():
        data = serializer.data

    assert len(data["availabilities"]) == 1
    avail_data = data["availabilities"][0]
    assert set(avail_data.keys()) == {"start", "end", "allDay"}
    assert avail_data["start"] == avail.start.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert avail_data["end"] == avail.end.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.mark.django_db
def test_room_orga_serializer_create_sets_event():
    with scopes_disabled():
        event = EventFactory()
    request = make_api_request(event)

    serializer = RoomOrgaSerializer(
        data={"name": "Main Hall", "position": 0}, context={"request": request}
    )
    serializer.is_valid(raise_exception=True)

    with scopes_disabled():
        room = serializer.save()

    assert room.event == event
    assert str(room.name) == "Main Hall"


@pytest.mark.django_db
def test_room_orga_serializer_create_with_availabilities():
    with scopes_disabled():
        event = EventFactory()
    request = make_api_request(event)
    start = event.datetime_from.isoformat()
    end = (event.datetime_from + dt.timedelta(hours=2)).isoformat()

    serializer = RoomOrgaSerializer(
        data={
            "name": "Side Room",
            "position": 1,
            "availabilities": [{"start": start, "end": end}],
        },
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)

    with scopes_disabled():
        room = serializer.save()

    with scopes_disabled():
        assert room.availabilities.count() == 1
        avail = room.availabilities.first()
        assert avail.event == event


@pytest.mark.django_db
def test_room_orga_serializer_create_without_availabilities():
    with scopes_disabled():
        event = EventFactory()
    request = make_api_request(event)

    serializer = RoomOrgaSerializer(
        data={"name": "No Avail Room", "position": 2}, context={"request": request}
    )
    serializer.is_valid(raise_exception=True)

    with scopes_disabled():
        room = serializer.save()

    with scopes_disabled():
        assert room.availabilities.count() == 0


@pytest.mark.django_db
def test_room_orga_serializer_update():
    with scopes_disabled():
        room = RoomFactory()
    request = make_api_request(room.event)

    serializer = RoomOrgaSerializer(
        room, data={"name": "Renamed Hall", "position": 5}, context={"request": request}
    )
    serializer.is_valid(raise_exception=True)

    with scopes_disabled():
        updated = serializer.save()

    assert str(updated.name) == "Renamed Hall"
    assert updated.position == 5


@pytest.mark.django_db
def test_room_orga_serializer_update_with_availabilities():
    with scopes_disabled():
        room = RoomFactory()
        AvailabilityFactory(event=room.event, room=room)
    request = make_api_request(room.event)
    new_start = room.event.datetime_from.isoformat()
    new_end = (room.event.datetime_from + dt.timedelta(hours=3)).isoformat()

    serializer = RoomOrgaSerializer(
        room,
        data={
            "name": str(room.name),
            "position": room.position,
            "availabilities": [{"start": new_start, "end": new_end}],
        },
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)

    with scopes_disabled():
        updated = serializer.save()

    with scopes_disabled():
        assert updated.availabilities.count() == 1


@pytest.mark.django_db
def test_room_orga_serializer_update_without_availabilities_key():
    """When availabilities key is absent from data, existing availabilities are untouched."""
    with scopes_disabled():
        room = RoomFactory()
        AvailabilityFactory(event=room.event, room=room)
    request = make_api_request(room.event)

    serializer = RoomOrgaSerializer(
        room,
        data={"name": "Partial Update"},
        partial=True,
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)

    with scopes_disabled():
        updated = serializer.save()

    with scopes_disabled():
        assert updated.availabilities.count() == 1


@pytest.mark.django_db
def test_room_orga_serializer_update_clear_availabilities():
    """Passing an empty availabilities list clears all existing ones."""
    with scopes_disabled():
        room = RoomFactory()
        AvailabilityFactory(event=room.event, room=room)
    request = make_api_request(room.event)

    serializer = RoomOrgaSerializer(
        room,
        data={"name": str(room.name), "position": room.position, "availabilities": []},
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)

    with scopes_disabled():
        updated = serializer.save()

    with scopes_disabled():
        assert updated.availabilities.count() == 0
