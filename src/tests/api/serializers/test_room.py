# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import uuid

import pytest

from pretalx.api.serializers.room import RoomOrgaSerializer, RoomSerializer
from pretalx.common.models.settings import GlobalSettings
from tests.factories import AvailabilityFactory, EventFactory, RoomFactory
from tests.utils import make_api_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_room_serializer_fields():
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


def test_room_serializer_uuid_without_guid():
    room = RoomFactory()
    request = make_api_request(room.event)

    serializer = RoomSerializer(room, context={"request": request})

    expected = str(
        uuid.uuid5(GlobalSettings().get_instance_identifier(), f"room:{room.pk}")
    )
    assert serializer.data["uuid"] == expected


def test_room_serializer_uuid_equals_guid_when_set():
    guid = uuid.uuid4()
    room = RoomFactory(guid=guid)
    request = make_api_request(room.event)

    serializer = RoomSerializer(room, context={"request": request})

    assert serializer.data["uuid"] == str(guid)
    assert serializer.data["guid"] == str(guid)


def test_room_orga_serializer_fields():
    room = RoomFactory()
    request = make_api_request(room.event)

    serializer = RoomOrgaSerializer(room, context={"request": request})
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


def test_room_orga_serializer_includes_availabilities():
    room = RoomFactory()
    avail = AvailabilityFactory(event=room.event, room=room)
    request = make_api_request(room.event)

    serializer = RoomOrgaSerializer(room, context={"request": request})
    data = serializer.data

    assert len(data["availabilities"]) == 1
    avail_data = data["availabilities"][0]
    assert set(avail_data.keys()) == {"start", "end", "allDay"}
    assert avail_data["start"] == avail.start.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert avail_data["end"] == avail.end.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_room_orga_serializer_create_with_availabilities():
    event = EventFactory()
    request = make_api_request(event)
    start = event.datetime_from.isoformat()
    end = (event.datetime_from + dt.timedelta(hours=2)).isoformat()

    serializer = RoomOrgaSerializer(
        data={
            "name": "Side Room",
            "position": 0,
            "availabilities": [{"start": start, "end": end}],
        },
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)

    room = serializer.save()

    assert room.event == event
    assert str(room.name) == "Side Room"
    assert room.availabilities.count() == 1
    avail = room.availabilities.first()
    assert avail.event == event


def test_room_orga_serializer_update():
    room = RoomFactory()
    request = make_api_request(room.event)

    serializer = RoomOrgaSerializer(
        room, data={"name": "Renamed Hall", "position": 5}, context={"request": request}
    )
    serializer.is_valid(raise_exception=True)

    updated = serializer.save()

    assert str(updated.name) == "Renamed Hall"
    assert updated.position == 5


def test_room_orga_serializer_update_with_availabilities():
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

    updated = serializer.save()

    assert updated.availabilities.count() == 1


def test_room_orga_serializer_update_without_availabilities_key():
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

    updated = serializer.save()

    assert updated.availabilities.count() == 1


def test_room_orga_serializer_update_clear_availabilities():
    room = RoomFactory()
    AvailabilityFactory(event=room.event, room=room)
    request = make_api_request(room.event)

    serializer = RoomOrgaSerializer(
        room,
        data={"name": str(room.name), "position": room.position, "availabilities": []},
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)

    updated = serializer.save()

    assert updated.availabilities.count() == 0
