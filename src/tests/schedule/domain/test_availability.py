# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest

from pretalx.schedule.domain.availability import (
    merged_speaker_availabilities,
    replace_availabilities,
)
from pretalx.schedule.models import Availability
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    AvailabilityFactory,
    RoomFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_replace_availabilities_for_room_and_speaker(event):
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    AvailabilityFactory(event=event, room=room)
    AvailabilityFactory(event=event, person=speaker)
    start = event.datetime_from + dt.timedelta(hours=1)
    end = event.datetime_to - dt.timedelta(hours=1)

    replace_availabilities(room, [Availability(event=event, start=start, end=end)])
    replace_availabilities(speaker, [Availability(event=event, start=start, end=end)])

    assert list(room.availabilities.values_list("start", "end")) == [(start, end)]
    assert list(speaker.availabilities.values_list("start", "end")) == [(start, end)]

    replace_availabilities(room, [])

    assert list(room.availabilities.all()) == []
    assert list(speaker.availabilities.values_list("start", "end")) == [(start, end)]


def test_merged_speaker_availabilities(event):
    start = event.datetime_from
    hour = dt.timedelta(hours=1)
    single = SpeakerFactory(event=event)
    AvailabilityFactory(event=event, person=single, start=start, end=start + 2 * hour)
    AvailabilityFactory(
        event=event, person=single, start=start + 2 * hour, end=start + 4 * hour
    )
    pair_a = SpeakerFactory(event=event)
    pair_b = SpeakerFactory(event=event)
    AvailabilityFactory(event=event, person=pair_a, start=start, end=start + 3 * hour)
    AvailabilityFactory(
        event=event, person=pair_b, start=start + hour, end=start + 5 * hour
    )
    unavailable = SpeakerFactory(event=event)
    slots = {}
    for key, speakers in (
        ("single", [single]),
        ("pair", [pair_a, pair_b]),
        ("mixed", [unavailable, pair_a]),
        ("none", [unavailable]),
    ):
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.set(speakers)
        slots[key] = TalkSlotFactory(submission=submission)
    TalkSlotFactory(
        schedule=event.wip_schedule,
        submission=None,
        room=RoomFactory(event=event),
        slot_type="break",
    )

    result = merged_speaker_availabilities(event.wip_schedule)

    assert {
        key: [(avail.start, avail.end) for avail in avails]
        for key, avails in result.items()
    } == {
        slots["single"].id: [(start, start + 4 * hour)],
        slots["pair"].id: [(start + hour, start + 3 * hour)],
        slots["mixed"].id: [(start, start + 3 * hour)],
        slots["none"].id: [],
    }
