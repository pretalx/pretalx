# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils.timezone import now as tz_now
from django_scopes import scope

from pretalx.schedule.domain.warnings import get_all_talk_warnings, get_talk_warnings
from pretalx.schedule.models import TalkSlot
from pretalx.schedule.models.slot import SlotType
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    AvailabilityFactory,
    EventFactory,
    RoomFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TrackFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_schedule_get_talk_warnings_empty_for_unscheduled(event):
    with scope(event=event):
        schedule = event.wip_schedule
    slot = TalkSlotFactory(
        submission=None, schedule=schedule, room=None, start=None, end=None
    )

    assert get_talk_warnings(schedule, slot) == []


@pytest.mark.parametrize(
    ("offset_a", "offset_b"),
    (
        ((0, 60), (0, 60)),
        ((0, 60), (0, 30)),
        ((0, 60), (30, 60)),
        ((0, 60), (0, 90)),
        ((0, 60), (15, 45)),
        ((0, 60), (-15, 15)),
    ),
    ids=[
        "exact",
        "shared_start",
        "shared_end",
        "shared_start_longer",
        "fully_contained",
        "partial_before",
    ],
)
def test_schedule_get_talk_warnings_room_overlap(event, offset_a, offset_b):
    room = RoomFactory(event=event)
    submission1 = SubmissionFactory(event=event)
    submission2 = SubmissionFactory(event=event)
    base = event.datetime_from
    with scope(event=event):
        schedule = event.wip_schedule
    slot1 = TalkSlotFactory(
        submission=submission1,
        schedule=schedule,
        room=room,
        start=base + dt.timedelta(minutes=offset_a[0]),
        end=base + dt.timedelta(minutes=offset_a[1]),
    )
    TalkSlotFactory(
        submission=submission2,
        schedule=schedule,
        room=room,
        start=base + dt.timedelta(minutes=offset_b[0]),
        end=base + dt.timedelta(minutes=offset_b[1]),
    )

    with scope(event=event):
        warnings = get_talk_warnings(schedule, slot1, with_speakers=False)
        bulk = get_all_talk_warnings(schedule)

    assert len(warnings) == 1
    assert warnings[0]["type"] == "room_overlap"
    assert len(bulk) == 2
    for slot_warnings in bulk.values():
        assert len(slot_warnings) == 1
        assert slot_warnings[0]["type"] == "room_overlap"


def test_schedule_get_all_talk_warnings_filter_updated_detects_conflict(event):
    room = RoomFactory(event=event)
    submission1 = SubmissionFactory(event=event)
    submission2 = SubmissionFactory(event=event)
    start = event.datetime_from
    end = start + dt.timedelta(hours=1)
    with scope(event=event):
        schedule = event.wip_schedule
    past = tz_now() - dt.timedelta(hours=2)
    stable_slot = TalkSlotFactory(
        submission=submission1, schedule=schedule, room=room, start=start, end=end
    )
    TalkSlot.objects.filter(pk=stable_slot.pk).update(updated=past)
    TalkSlotFactory(
        submission=submission2, schedule=schedule, room=room, start=start, end=end
    )

    cutoff = tz_now() - dt.timedelta(minutes=5)
    with scope(event=event):
        result = get_all_talk_warnings(schedule, filter_updated=cutoff)

    assert len(result) == 1
    (talk_warnings,) = result.values()
    assert len(talk_warnings) == 1
    assert talk_warnings[0]["type"] == "room_overlap"


def test_schedule_get_all_talk_warnings_non_overlapping(event):
    """Non-overlapping slots in the same room and with a shared speaker produce no warnings."""
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission1 = SubmissionFactory(event=event)
    submission2 = SubmissionFactory(event=event)
    submission1.speakers.add(speaker)
    submission2.speakers.add(speaker)
    start = event.datetime_from
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(
        submission=submission1,
        schedule=schedule,
        room=room,
        start=start,
        end=start + dt.timedelta(minutes=30),
    )
    TalkSlotFactory(
        submission=submission2,
        schedule=schedule,
        room=room,
        start=start + dt.timedelta(minutes=60),
        end=start + dt.timedelta(minutes=90),
    )

    with scope(event=event):
        result = get_all_talk_warnings(schedule)

    assert result == {}


def test_schedule_get_all_talk_warnings_filter_updated_speaker_overlap(event):
    """Subset mode detects speaker overlap against a non-updated slot."""
    room1 = RoomFactory(event=event)
    room2 = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission1 = SubmissionFactory(event=event)
    submission2 = SubmissionFactory(event=event)
    submission1.speakers.add(speaker)
    submission2.speakers.add(speaker)
    start = event.datetime_from
    end = start + dt.timedelta(hours=1)
    with scope(event=event):
        schedule = event.wip_schedule
    past = tz_now() - dt.timedelta(hours=2)
    stable_slot = TalkSlotFactory(
        submission=submission1, schedule=schedule, room=room1, start=start, end=end
    )
    TalkSlot.objects.filter(pk=stable_slot.pk).update(updated=past)
    TalkSlotFactory(
        submission=submission2, schedule=schedule, room=room2, start=start, end=end
    )

    cutoff = tz_now() - dt.timedelta(minutes=5)
    with scope(event=event):
        result = get_all_talk_warnings(schedule, filter_updated=cutoff)

    assert len(result) == 1
    (talk_warnings,) = result.values()
    assert len(talk_warnings) == 1
    assert talk_warnings[0]["type"] == "speaker"
    assert "another session" in talk_warnings[0]["message"]


def test_schedule_get_all_talk_warnings_filter_updated_no_overlap(event):
    """Subset mode handles the updated slot having no room or speaker conflicts."""
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission1 = SubmissionFactory(event=event)
    submission2 = SubmissionFactory(event=event)
    submission1.speakers.add(speaker)
    submission2.speakers.add(speaker)
    start = event.datetime_from
    with scope(event=event):
        schedule = event.wip_schedule
    past = tz_now() - dt.timedelta(hours=2)
    stable_slot = TalkSlotFactory(
        submission=submission1,
        schedule=schedule,
        room=room,
        start=start,
        end=start + dt.timedelta(minutes=30),
    )
    TalkSlot.objects.filter(pk=stable_slot.pk).update(updated=past)
    TalkSlotFactory(
        submission=submission2,
        schedule=schedule,
        room=room,
        start=start + dt.timedelta(minutes=60),
        end=start + dt.timedelta(minutes=90),
    )

    cutoff = tz_now() - dt.timedelta(minutes=5)
    with scope(event=event):
        result = get_all_talk_warnings(schedule, filter_updated=cutoff)

    assert result == {}


def test_schedule_get_all_talk_warnings_breaks(event):
    """Breaks participate in overlap detection when well-formed and are skipped otherwise."""
    room = RoomFactory(event=event)
    submission = SubmissionFactory(event=event)
    start = event.datetime_from
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(
        submission=None,
        schedule=schedule,
        room=room,
        slot_type=SlotType.BREAK,
        start=start,
        end=None,
    )
    TalkSlotFactory(
        submission=None,
        schedule=schedule,
        room=room,
        slot_type=SlotType.BREAK,
        start=start + dt.timedelta(hours=4),
        end=start + dt.timedelta(hours=5),
    )
    TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=start + dt.timedelta(hours=2),
        end=start + dt.timedelta(hours=3),
    )

    with scope(event=event):
        result = get_all_talk_warnings(schedule)

    assert result == {}


def test_schedule_get_all_talk_warnings_slot_without_end(event):
    """Slots with start set but end unset fall back to submission duration."""
    room = RoomFactory(event=event)
    submission1 = SubmissionFactory(event=event)
    submission2 = SubmissionFactory(event=event)
    start = event.datetime_from
    with scope(event=event):
        schedule = event.wip_schedule
    open_slot = TalkSlotFactory(
        submission=submission1, schedule=schedule, room=room, start=start, end=None
    )
    overlapping_slot = TalkSlotFactory(
        submission=submission2,
        schedule=schedule,
        room=room,
        start=start + dt.timedelta(minutes=5),
        end=start + dt.timedelta(minutes=20),
    )

    with scope(event=event):
        bulk = get_all_talk_warnings(schedule)

    assert set(bulk.keys()) == {open_slot, overlapping_slot}
    for slot_warnings in bulk.values():
        assert len(slot_warnings) == 1
        assert slot_warnings[0]["type"] == "room_overlap"


def test_schedule_get_talk_warnings_room_availability(event):
    room = RoomFactory(event=event)
    AvailabilityFactory(
        event=event,
        room=room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=2),
    )
    submission = SubmissionFactory(event=event)
    late_start = event.datetime_from + dt.timedelta(hours=10)
    with scope(event=event):
        schedule = event.wip_schedule
    slot = TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=late_start,
        end=late_start + dt.timedelta(hours=1),
    )

    with scope(event=event):
        warnings = get_talk_warnings(schedule, slot, with_speakers=False)

    assert len(warnings) == 1
    assert warnings[0]["type"] == "room"


@pytest.mark.parametrize(
    ("offset_a", "offset_b"),
    (
        ((0, 60), (0, 60)),
        ((0, 60), (0, 30)),
        ((0, 60), (30, 60)),
        ((0, 60), (15, 45)),
        ((0, 60), (-15, 15)),
    ),
    ids=["exact", "shared_start", "shared_end", "fully_contained", "partial_before"],
)
def test_schedule_get_talk_warnings_speaker_overlap(event, offset_a, offset_b):
    room1 = RoomFactory(event=event)
    room2 = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission1 = SubmissionFactory(event=event)
    submission2 = SubmissionFactory(event=event)
    submission1.speakers.add(speaker)
    submission2.speakers.add(speaker)
    base = event.datetime_from
    with scope(event=event):
        schedule = event.wip_schedule
    slot1 = TalkSlotFactory(
        submission=submission1,
        schedule=schedule,
        room=room1,
        start=base + dt.timedelta(minutes=offset_a[0]),
        end=base + dt.timedelta(minutes=offset_a[1]),
    )
    TalkSlotFactory(
        submission=submission2,
        schedule=schedule,
        room=room2,
        start=base + dt.timedelta(minutes=offset_b[0]),
        end=base + dt.timedelta(minutes=offset_b[1]),
    )

    with scope(event=event):
        warnings = get_talk_warnings(schedule, slot1, with_speakers=True)
        bulk = get_all_talk_warnings(schedule)

    speaker_warnings = [w for w in warnings if w["type"] == "speaker"]
    assert len(speaker_warnings) == 1
    assert "another session" in speaker_warnings[0]["message"]
    assert speaker_warnings[0]["speaker"]["code"] == speaker.code
    assert len(bulk) == 2
    for slot_warnings in bulk.values():
        bulk_speaker_warnings = [w for w in slot_warnings if w["type"] == "speaker"]
        assert len(bulk_speaker_warnings) == 1
        assert "another session" in bulk_speaker_warnings[0]["message"]


def test_schedule_get_talk_warnings_speaker_availability(event):
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    AvailabilityFactory(
        event=event,
        person=speaker,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    late_start = event.datetime_from + dt.timedelta(hours=10)
    with scope(event=event):
        schedule = event.wip_schedule
    slot = TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=late_start,
        end=late_start + dt.timedelta(hours=1),
    )

    with scope(event=event):
        warnings = get_talk_warnings(schedule, slot, with_speakers=True)

    speaker_warnings = [w for w in warnings if w["type"] == "speaker"]
    assert len(speaker_warnings) == 1
    assert speaker_warnings[0]["speaker"]["code"] == speaker.code


def test_schedule_get_talk_warnings_no_speaker_avail_when_disabled(event):
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    AvailabilityFactory(
        event=event,
        person=speaker,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )
    submission = SubmissionFactory(event=event)
    submission.speakers.add(speaker)
    late_start = event.datetime_from + dt.timedelta(hours=10)
    with scope(event=event):
        schedule = event.wip_schedule
    slot = TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=late_start,
        end=late_start + dt.timedelta(hours=1),
    )

    with scope(event=event):
        warnings = get_talk_warnings(schedule, slot, with_speakers=False)

    speaker_avail_warnings = [
        w
        for w in warnings
        if w["type"] == "speaker" and "not available" in w["message"]
    ]
    assert speaker_avail_warnings == []


def test_schedule_get_all_talk_warnings_filter_updated(event):
    room = RoomFactory(event=event)
    submission = SubmissionFactory(event=event)
    start = event.datetime_from
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=start,
        end=start + dt.timedelta(hours=1),
    )

    future = tz_now() + dt.timedelta(hours=1)
    with scope(event=event):
        result = get_all_talk_warnings(schedule, filter_updated=future)

    assert result == {}


def test_schedule_get_talk_warnings_room_avail_contains(event):
    room = RoomFactory(event=event)
    avail = AvailabilityFactory(
        event=event, room=room, start=event.datetime_from, end=event.datetime_to
    )
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        schedule = event.wip_schedule
    slot = TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )

    with scope(event=event):
        warnings = get_talk_warnings(
            schedule, slot, with_speakers=False, room_avails=[avail]
        )

    room_warnings = [w for w in warnings if w["type"] == "room"]
    assert room_warnings == []


def test_schedule_get_talk_warnings_room_avails_none(event):
    """When room_avails is not passed, it fetches them from the room."""
    room = RoomFactory(event=event)
    AvailabilityFactory(
        event=event,
        room=room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=2),
    )
    submission = SubmissionFactory(event=event)
    late_start = event.datetime_from + dt.timedelta(hours=10)
    with scope(event=event):
        schedule = event.wip_schedule
    slot = TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=late_start,
        end=late_start + dt.timedelta(hours=1),
    )

    with scope(event=event):
        warnings = get_talk_warnings(
            schedule, slot, with_speakers=False, room_avails=None
        )

    assert len(warnings) == 1
    assert warnings[0]["type"] == "room"


def test_schedule_warnings_unscheduled_count(event):
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(
        submission=submission, schedule=schedule, room=None, start=None, end=None
    )

    with scope(event=event):
        result = schedule.warnings

    assert result["unscheduled"] == 1


def test_schedule_warnings_unconfirmed_count(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    room = RoomFactory(event=event)
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )

    with scope(event=event):
        result = schedule.warnings

    assert result["unconfirmed"] == 1


def test_schedule_warnings_no_track_when_tracks_enabled():
    event = EventFactory(feature_flags={"use_tracks": True})
    TrackFactory(event=event)
    submission = SubmissionFactory(event=event, track=None)
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(submission=submission, schedule=schedule)

    with scope(event=event):
        result = schedule.warnings

    assert result["no_track"].count() == 1


def test_schedule_warnings_no_track_empty_when_tracks_disabled():
    event = EventFactory(feature_flags={"use_tracks": False})
    submission = SubmissionFactory(event=event, track=None)
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(submission=submission, schedule=schedule)

    with scope(event=event):
        result = schedule.warnings

    assert result["no_track"] == []
