import datetime as dt

import pytest
from django_scopes import scopes_disabled

from pretalx.api.serializers.availability import (
    AvailabilitiesMixin,
    AvailabilitySerializer,
)
from pretalx.schedule.models import Availability
from tests.factories import AvailabilityFactory, EventFactory, RoomFactory

pytestmark = pytest.mark.unit


def test_availability_serializer_fields():
    avail = Availability(
        start=dt.datetime(2024, 1, 1, 9, 0, tzinfo=dt.UTC),
        end=dt.datetime(2024, 1, 1, 17, 0, tzinfo=dt.UTC),
    )
    data = AvailabilitySerializer(avail).data
    assert set(data.keys()) == {"start", "end", "allDay"}


@pytest.mark.parametrize(
    ("start_time", "end_time", "expected_all_day"),
    (
        (dt.time(0, 0), dt.time(0, 0), True),
        (dt.time(9, 0), dt.time(17, 0), False),
        (dt.time(0, 0), dt.time(17, 0), False),
        (dt.time(9, 0), dt.time(0, 0), False),
    ),
    ids=[
        "midnight_to_midnight",
        "partial_day",
        "midnight_start_only",
        "midnight_end_only",
    ],
)
def test_availability_serializer_all_day(start_time, end_time, expected_all_day):
    avail = Availability(
        start=dt.datetime.combine(dt.date(2024, 1, 1), start_time, tzinfo=dt.UTC),
        end=dt.datetime.combine(dt.date(2024, 1, 2), end_time, tzinfo=dt.UTC),
    )
    data = AvailabilitySerializer(avail).data
    assert data["allDay"] is expected_all_day


@pytest.mark.django_db
def test_availabilities_mixin_handle_availabilities_replaces_existing():
    """Existing availabilities are deleted and new ones are created."""
    event = EventFactory()
    room = RoomFactory(event=event)
    AvailabilityFactory(event=event, room=room)

    with scopes_disabled():
        old_pk = room.availabilities.first().pk

    mixin = AvailabilitiesMixin()
    mixin.event = event

    new_start = event.datetime_from
    new_end = event.datetime_from + dt.timedelta(hours=2)
    with scopes_disabled():
        mixin._handle_availabilities(
            room, [{"start": new_start, "end": new_end}], "room"
        )

        avails = list(room.availabilities.all())
    assert len(avails) == 1
    assert avails[0].pk != old_pk
    assert avails[0].start == new_start
    assert avails[0].end == new_end
    assert avails[0].room == room
    assert avails[0].event == event


@pytest.mark.django_db
def test_availabilities_mixin_handle_availabilities_merges_overlapping():
    """Overlapping availability ranges are merged into a single range."""
    event = EventFactory()
    room = RoomFactory(event=event)

    mixin = AvailabilitiesMixin()
    mixin.event = event

    start = event.datetime_from
    end = start + dt.timedelta(hours=4)
    with scopes_disabled():
        mixin._handle_availabilities(
            room,
            [
                {"start": start, "end": start + dt.timedelta(hours=3)},
                {"start": start + dt.timedelta(hours=2), "end": end},
            ],
            "room",
        )

        avails = list(room.availabilities.all())
    assert len(avails) == 1
    assert avails[0].start == start
    assert avails[0].end == end


@pytest.mark.django_db
def test_availabilities_mixin_handle_availabilities_keeps_non_overlapping_separate():
    """Non-overlapping availability ranges stay as separate entries."""
    event = EventFactory()
    room = RoomFactory(event=event)

    mixin = AvailabilitiesMixin()
    mixin.event = event

    start1 = event.datetime_from
    end1 = start1 + dt.timedelta(hours=1)
    start2 = start1 + dt.timedelta(hours=3)
    end2 = start2 + dt.timedelta(hours=1)

    with scopes_disabled():
        mixin._handle_availabilities(
            room,
            [{"start": start1, "end": end1}, {"start": start2, "end": end2}],
            "room",
        )

        avails = list(room.availabilities.order_by("start"))
    assert len(avails) == 2
    assert avails[0].start == start1
    assert avails[0].end == end1
    assert avails[1].start == start2
    assert avails[1].end == end2


@pytest.mark.django_db
def test_availabilities_mixin_handle_availabilities_empty_deletes_all():
    """Empty availability list removes all existing availabilities."""
    event = EventFactory()
    room = RoomFactory(event=event)
    AvailabilityFactory(event=event, room=room)

    with scopes_disabled():
        assert room.availabilities.count() == 1

        mixin = AvailabilitiesMixin()
        mixin.event = event
        mixin._handle_availabilities(room, [], "room")

        assert room.availabilities.count() == 0
