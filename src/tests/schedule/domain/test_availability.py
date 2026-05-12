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


def test_merged_speaker_availabilities_single_speaker(event):
    speaker = SpeakerFactory(event=event)
    AvailabilityFactory(event=event, person=speaker)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    slot = TalkSlotFactory(submission=submission)

    result = merged_speaker_availabilities(event.wip_schedule)

    assert slot.id in result
    assert len(result[slot.id]) == 1
    assert isinstance(result[slot.id][0], Availability)


def test_merged_speaker_availabilities_single_speaker_unions_adjacent(event):
    speaker = SpeakerFactory(event=event)
    mid = event.datetime_from + dt.timedelta(hours=2)
    AvailabilityFactory(event=event, person=speaker, start=event.datetime_from, end=mid)
    AvailabilityFactory(event=event, person=speaker, start=mid, end=event.datetime_to)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    slot = TalkSlotFactory(submission=submission)

    result = merged_speaker_availabilities(event.wip_schedule)

    assert len(result[slot.id]) == 1


def test_merged_speaker_availabilities_multi_speaker_intersection(event):
    speaker_a = SpeakerFactory(event=event)
    speaker_b = SpeakerFactory(event=event)
    AvailabilityFactory(event=event, person=speaker_a)
    AvailabilityFactory(event=event, person=speaker_b)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker_a)
    submission.speakers.add(speaker_b)
    slot = TalkSlotFactory(submission=submission)

    result = merged_speaker_availabilities(event.wip_schedule)

    assert slot.id in result
    assert len(result[slot.id]) == 1


def test_merged_speaker_availabilities_no_availabilities(event):
    speaker_a = SpeakerFactory(event=event)
    speaker_b = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker_a)
    submission.speakers.add(speaker_b)
    slot = TalkSlotFactory(submission=submission)

    result = merged_speaker_availabilities(event.wip_schedule)

    assert result[slot.id] == []


def test_merged_speaker_availabilities_skips_submissionless_slots(event):
    speaker = SpeakerFactory(event=event)
    AvailabilityFactory(event=event, person=speaker)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    slot = TalkSlotFactory(submission=submission)
    room = RoomFactory(event=event)
    TalkSlotFactory(
        schedule=event.wip_schedule, submission=None, room=room, slot_type="break"
    )

    result = merged_speaker_availabilities(event.wip_schedule)

    assert set(result) == {slot.id}
