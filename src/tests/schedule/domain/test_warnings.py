# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils.timezone import now as tz_now
from django_scopes import scope

from pretalx.schedule.domain.release import freeze_schedule
from pretalx.schedule.domain.warnings import (
    compute_signup_warnings,
    get_all_talk_warnings,
    get_talk_warnings,
    overbooked_slots_for_room,
)
from pretalx.schedule.models import TalkSlot
from pretalx.schedule.models.slot import SlotType
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    AttendeeSignupFactory,
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


def _signup_event(**flags):
    flags.setdefault("attendee_signup", True)
    return EventFactory(feature_flags=flags)


def _required_signup_slot(
    event,
    *,
    room_capacity,
    session_capacity=None,
    state=SubmissionStates.CONFIRMED,
    is_visible=True,
):
    sub_type = event.cfp.default_type
    sub_type.attendee_signup_required = True
    sub_type.save()
    room = RoomFactory(event=event, capacity=room_capacity)
    submission = SubmissionFactory(
        event=event,
        state=state,
        submission_type=sub_type,
        attendee_signup_capacity=session_capacity,
    )
    start = event.datetime_from
    slot = TalkSlotFactory(
        submission=submission,
        schedule=event.wip_schedule,
        room=room,
        start=start,
        end=start + dt.timedelta(hours=1),
        is_visible=is_visible,
    )
    return submission, slot


def test_signup_capacity_warnings_room_too_small_in_editor():
    event = _signup_event()
    submission, slot = _required_signup_slot(
        event, room_capacity=20, session_capacity=50
    )

    with scope(event=event):
        warnings = get_talk_warnings(event.wip_schedule, slot, with_speakers=False)

    assert [w["type"] for w in warnings] == ["signup_room_too_small"]
    assert "20" in warnings[0]["message"]
    assert "50" in warnings[0]["message"]


def test_signup_capacity_warnings_overfull_is_release_only():
    event = _signup_event()
    submission, slot = _required_signup_slot(event, room_capacity=5, session_capacity=5)
    for _ in range(6):
        AttendeeSignupFactory(submission=submission)

    with scope(event=event):
        editor_warnings = get_talk_warnings(
            event.wip_schedule, slot, with_speakers=False
        )

    assert "signup_overfull" not in [w["type"] for w in editor_warnings]


@pytest.mark.parametrize(
    ("feature_on", "signup_required", "room_capacity", "session_capacity"),
    (
        (True, False, 10, 500),  # session does not require signup
        (True, True, 10, None),  # signup capacity not set
        (True, True, None, 50),  # room capacity not set
        (False, True, 5, 50),  # feature flag off
    ),
)
def test_signup_capacity_warnings_empty(
    feature_on, signup_required, room_capacity, session_capacity
):
    event = EventFactory(feature_flags={"attendee_signup": feature_on})
    sub_type = event.cfp.default_type
    sub_type.attendee_signup_required = signup_required
    sub_type.save()
    room = RoomFactory(event=event, capacity=room_capacity)
    submission = SubmissionFactory(
        event=event,
        state=SubmissionStates.CONFIRMED,
        submission_type=sub_type,
        attendee_signup_capacity=session_capacity,
    )
    start = event.datetime_from
    slot = TalkSlotFactory(
        submission=submission,
        schedule=event.wip_schedule,
        room=room,
        start=start,
        end=start + dt.timedelta(hours=1),
        is_visible=True,
    )

    with scope(event=event):
        warnings = get_talk_warnings(event.wip_schedule, slot, with_speakers=False)

    assert [w for w in warnings if w["type"].startswith("signup_")] == []


def test_compute_signup_warnings_room_too_large():
    event = _signup_event()
    submission, slot = _required_signup_slot(
        event, room_capacity=100, session_capacity=40
    )

    with scope(event=event):
        warnings = compute_signup_warnings(event.wip_schedule)

    assert [entry["submission"] for entry in warnings["signup_room_too_large"]] == [
        submission
    ]
    assert warnings["signup_room_too_large"][0]["current_capacity"] == 40
    assert warnings["signup_room_too_large"][0]["room_capacity"] == 100
    assert warnings["signup_overfull"] == []


def test_compute_signup_warnings_room_too_small_is_per_talk_only():
    event = _signup_event()
    _required_signup_slot(event, room_capacity=10, session_capacity=100)

    with scope(event=event):
        release_warnings = compute_signup_warnings(event.wip_schedule)

    assert "signup_room_too_small" not in release_warnings
    assert release_warnings["signup_room_too_large"] == []


def test_compute_signup_warnings_room_overfull():
    event = _signup_event()
    submission, slot = _required_signup_slot(event, room_capacity=2, session_capacity=2)
    for _ in range(3):
        AttendeeSignupFactory(submission=submission)

    with scope(event=event):
        warnings = compute_signup_warnings(event.wip_schedule)

    assert [entry["submission"] for entry in warnings["signup_overfull"]] == [
        submission
    ]
    assert warnings["signup_overfull"][0]["signup_count"] == 3


def test_compute_signup_warnings_no_capacity_flags_session_and_room_both_unset():
    event = _signup_event()
    submission, slot = _required_signup_slot(
        event, room_capacity=None, session_capacity=None
    )

    with scope(event=event):
        warnings = compute_signup_warnings(event.wip_schedule)

    assert [entry["submission"] for entry in warnings["signup_no_capacity"]] == [
        submission
    ]
    assert warnings["signup_no_capacity"][0]["slot"] == slot


@pytest.mark.parametrize(
    ("room_capacity", "session_capacity"),
    (
        (None, 50),  # session capacity set, room capacity unset
        (20, None),  # room capacity set, session capacity unset
    ),
)
def test_compute_signup_warnings_no_capacity_silent_when_any_capacity_set(
    room_capacity, session_capacity
):
    event = _signup_event()
    _required_signup_slot(
        event, room_capacity=room_capacity, session_capacity=session_capacity
    )

    with scope(event=event):
        warnings = compute_signup_warnings(event.wip_schedule)

    assert warnings["signup_no_capacity"] == []


@pytest.mark.parametrize("room_capacity", (None, 10))
def test_compute_signup_warnings_ignores_signup_not_required(room_capacity):
    """When the session does not require signup, no warnings fire — even
    when the room has no capacity (the no-capacity branch) or has one
    (the scheduled-slots branch)."""
    event = _signup_event()
    room = RoomFactory(event=event, capacity=room_capacity)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.attendee_signup_required = False
    submission.save()
    start = event.datetime_from
    TalkSlotFactory(
        submission=submission,
        schedule=event.wip_schedule,
        room=room,
        start=start,
        end=start + dt.timedelta(hours=1),
        is_visible=True,
    )

    with scope(event=event):
        warnings = compute_signup_warnings(event.wip_schedule)

    assert warnings == {
        "signup_room_too_large": [],
        "signup_no_capacity": [],
        "signup_overfull": [],
        "signup_dropped_with_attendees": [],
    }


@pytest.mark.parametrize("with_signup", (True, False))
def test_compute_signup_warnings_dropped_session(with_signup):
    """A dropped session (was in previous release, no longer scheduled)
    only fires the warning when it has signups to strand."""
    event = _signup_event()
    submission, _slot = _required_signup_slot(event, room_capacity=50)
    if with_signup:
        AttendeeSignupFactory(submission=submission)
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        wip = event.wip_schedule
        wip.talks.update(room=None, start=None, end=None, is_visible=False)

    with scope(event=event):
        warnings = compute_signup_warnings(wip)

    dropped = warnings["signup_dropped_with_attendees"]
    if with_signup:
        assert [entry["submission"] for entry in dropped] == [submission]
        assert dropped[0]["signup_count"] == 1
    else:
        assert dropped == []


def test_compute_signup_warnings_previous_schedule_no_drops_silent():
    event = _signup_event()
    submission, _slot = _required_signup_slot(event, room_capacity=50)
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        wip = event.wip_schedule

    with scope(event=event):
        warnings = compute_signup_warnings(wip)

    assert warnings["signup_dropped_with_attendees"] == []


def test_schedule_warnings_talk_warnings_count_sums_per_talk_warnings():
    event = _signup_event()
    _submission, slot = _required_signup_slot(
        event, room_capacity=4, session_capacity=600
    )
    other_submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scope(event=event):
        TalkSlotFactory(
            submission=other_submission,
            schedule=event.wip_schedule,
            room=slot.room,
            start=slot.start,
            end=slot.end,
            is_visible=True,
        )
        warnings = event.wip_schedule.warnings

    # Two talks, but the signup-required one carries two warnings
    # (signup_room_too_small + room_overlap), so total = 3.
    assert len(warnings["talk_warnings"]) == 2
    assert warnings["talk_warnings_count"] == sum(
        len(entry["warnings"]) for entry in warnings["talk_warnings"]
    )
    assert warnings["talk_warnings_count"] == 3


def test_schedule_warnings_signup_lists_empty_when_feature_off():
    event = EventFactory(feature_flags={"attendee_signup": False})
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    room = RoomFactory(event=event, capacity=5)
    with scope(event=event):
        TalkSlotFactory(
            submission=submission,
            schedule=event.wip_schedule,
            room=room,
            start=event.datetime_from,
            end=event.datetime_from + dt.timedelta(hours=1),
        )
        warnings = event.wip_schedule.warnings

    assert warnings["signup_room_too_large"] == []
    assert warnings["signup_no_capacity"] == []
    assert warnings["signup_overfull"] == []
    assert warnings["signup_dropped_with_attendees"] == []


def test_get_all_talk_warnings_includes_signup_warning_when_room_too_small():
    event = _signup_event()
    _required_signup_slot(event, room_capacity=10, session_capacity=80)

    with scope(event=event):
        result = get_all_talk_warnings(event.wip_schedule)

    (annotated_slot,) = result.keys()
    (talk_warnings,) = result.values()
    assert "signup_room_too_small" in [w["type"] for w in talk_warnings]
    # Slots are annotated with ``_annotated_requires_signup`` so the helper
    # below can short-circuit without re-querying.
    assert annotated_slot._annotated_requires_signup is True


def test_signup_capacity_warnings_prefers_slot_annotation():
    event = _signup_event()
    submission, slot = _required_signup_slot(
        event, room_capacity=10, session_capacity=80
    )
    # Force the annotation to claim the session does NOT require signup,
    # then verify the helper trusts the annotation over the cached_property.
    slot._annotated_requires_signup = False

    with scope(event=event):
        warnings = get_talk_warnings(event.wip_schedule, slot, with_speakers=False)

    assert [w for w in warnings if w["type"].startswith("signup_")] == []


def test_compute_signup_warnings_includes_invisible_scheduled_slot():
    """Warnings operate on the same scheduled-slot set (room + start) as
    defaults and dropped-detection, ignoring ``is_visible``, so the
    organiser sees what the freeze will actually do."""
    event = _signup_event()
    submission, _slot = _required_signup_slot(
        event, room_capacity=100, session_capacity=20, is_visible=False
    )

    with scope(event=event):
        warnings = compute_signup_warnings(event.wip_schedule)

    assert [entry["submission"] for entry in warnings["signup_room_too_large"]] == [
        submission
    ]


def test_compute_signup_warnings_dropped_ignores_visibility_toggle():
    """A slot whose ``is_visible`` flag was toggled but whose room + start
    were not cleared, and whose submission is still CONFIRMED, must NOT
    register as dropped: the freeze will re-set visibility from the state
    on release.
    """
    event = _signup_event()
    submission, _slot = _required_signup_slot(event, room_capacity=50)
    AttendeeSignupFactory(submission=submission)
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        wip = event.wip_schedule
        wip.talks.update(is_visible=False)

    with scope(event=event):
        warnings = compute_signup_warnings(wip)

    assert warnings["signup_dropped_with_attendees"] == []


def test_compute_signup_warnings_dropped_detects_unconfirmed_after_release():
    """A slot that retains its room+start but whose submission has been
    withdrawn / rejected / cancelled since the previous release must
    register as dropped: ``freeze_schedule`` only marks ``state=CONFIRMED``
    slots visible, so the session would silently vanish from the next
    release and its signups would be stranded.
    """
    event = _signup_event()
    submission, _slot = _required_signup_slot(event, room_capacity=50)
    AttendeeSignupFactory(submission=submission)
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        wip = event.wip_schedule
        submission.state = SubmissionStates.CANCELED
        submission.save()

    with scope(event=event):
        warnings = compute_signup_warnings(wip)

    dropped = warnings["signup_dropped_with_attendees"]
    assert [entry["submission"] for entry in dropped] == [submission]
    assert dropped[0]["signup_count"] == 1


def test_compute_signup_warnings_current_capacity_zero_is_not_treated_as_unset():
    """When an organiser sets the signup capacity to ``0`` (signup closed),
    the comparison must use ``0`` instead of falling back to the room
    capacity (``explicit_capacity or room_capacity``), otherwise both
    room-too-large and overfull warnings get suppressed.
    """
    event = _signup_event()
    submission, _slot = _required_signup_slot(
        event, room_capacity=20, session_capacity=None
    )
    # The model validator floors capacity at 1 for new input, but stored
    # rows might end up with 0 from data migrations or admin tooling.
    # Bypass the validator with an UPDATE.
    submission.__class__.objects.filter(pk=submission.pk).update(
        attendee_signup_capacity=0
    )

    with scope(event=event):
        warnings = compute_signup_warnings(event.wip_schedule)

    too_large = warnings["signup_room_too_large"]
    assert [entry["submission"] for entry in too_large] == [submission]
    assert too_large[0]["current_capacity"] == 0


@pytest.mark.parametrize(
    ("room_capacity", "signup_count", "expect_overbooked"),
    (
        (5, 3, False),  # below capacity
        (3, 4, True),  # over capacity
        (None, 6, False),  # unlimited capacity, never overbooked
    ),
)
def test_overbooked_slots_for_room(room_capacity, signup_count, expect_overbooked):
    event = _signup_event()
    submission, slot = _required_signup_slot(event, room_capacity=room_capacity)
    for _ in range(signup_count):
        AttendeeSignupFactory(submission=submission)

    with scope(event=event):
        result = list(overbooked_slots_for_room(slot.room))

    assert result == ([slot] if expect_overbooked else [])


def test_overbooked_slots_for_room_ignores_other_rooms():
    event = _signup_event()
    _submission, slot = _required_signup_slot(event, room_capacity=1)
    other_room = RoomFactory(event=event, capacity=1)
    other_submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    other_submission.attendee_signup_required = True
    other_submission.save()
    TalkSlotFactory(
        submission=other_submission,
        schedule=event.wip_schedule,
        room=other_room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )
    for _ in range(20):
        AttendeeSignupFactory(submission=other_submission)

    with scope(event=event):
        assert list(overbooked_slots_for_room(slot.room)) == []


def test_overbooked_slots_for_room_ignores_unscheduled_slots():
    """Slots without a ``start`` are not in the room yet — they can't be
    overbooked even if their submission has signups."""
    event = _signup_event()
    sub_type = event.cfp.default_type
    sub_type.attendee_signup_required = True
    sub_type.save()
    room = RoomFactory(event=event, capacity=1)
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.CONFIRMED, submission_type=sub_type
    )
    TalkSlotFactory(
        submission=submission,
        schedule=event.wip_schedule,
        room=room,
        start=None,
        end=None,
    )
    for _ in range(5):
        AttendeeSignupFactory(submission=submission)

    with scope(event=event):
        assert list(overbooked_slots_for_room(room)) == []
