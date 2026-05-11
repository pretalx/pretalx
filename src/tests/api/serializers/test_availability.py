# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest

from pretalx.api.serializers.availability import (
    AvailabilitySerializer,
    replace_from_serializer_data,
)
from pretalx.schedule.models import Availability
from tests.factories import AvailabilityFactory, EventFactory, RoomFactory

pytestmark = pytest.mark.unit


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
def test_replace_from_serializer_data_merges_overlapping():
    event = EventFactory()
    room = RoomFactory(event=event)
    AvailabilityFactory(event=event, room=room)

    start = event.datetime_from
    end = start + dt.timedelta(hours=4)
    replace_from_serializer_data(
        event=event,
        instance=room,
        availabilities_data=[
            {"start": start, "end": start + dt.timedelta(hours=3)},
            {"start": start + dt.timedelta(hours=2), "end": end},
        ],
    )

    avails = list(room.availabilities.all())
    assert len(avails) == 1
    assert avails[0].start == start
    assert avails[0].end == end
    assert avails[0].room == room
    assert avails[0].event == event
