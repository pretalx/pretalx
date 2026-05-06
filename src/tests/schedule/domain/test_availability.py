# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest

from pretalx.schedule.domain.availability import replace_availabilities
from pretalx.schedule.models import Availability
from tests.factories import AvailabilityFactory, RoomFactory, SpeakerFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_replace_availabilities_for_room(event):
    room = RoomFactory(event=event)
    AvailabilityFactory(event=event, room=room)
    new_start = event.datetime_from + dt.timedelta(hours=1)
    new_end = event.datetime_to - dt.timedelta(hours=1)
    new_avails = [Availability(event=event, room=room, start=new_start, end=new_end)]

    replace_availabilities(room, new_avails)
    result = list(room.availabilities.all())

    assert len(result) == 1
    assert result[0].start == new_start
    assert result[0].end == new_end


def test_replace_availabilities_for_speaker(event):
    speaker = SpeakerFactory(event=event)
    AvailabilityFactory(event=event, person=speaker)
    new_avails = [
        Availability(
            event=event,
            person=speaker,
            start=event.datetime_from,
            end=event.datetime_to,
        )
    ]

    replace_availabilities(speaker, new_avails)
    result = list(speaker.availabilities.all())

    assert len(result) == 1


def test_replace_availabilities_with_empty_list_clears(event):
    room = RoomFactory(event=event)
    AvailabilityFactory(event=event, room=room)

    replace_availabilities(room, [])

    assert list(room.availabilities.all()) == []
