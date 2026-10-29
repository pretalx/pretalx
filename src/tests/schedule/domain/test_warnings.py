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
from pretalx.submission.models import Submission, SubmissionStates
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


def _types(warnings):
    return sorted(warning["type"] for warning in warnings)


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
def test_schedule_get_talk_warnings_room_and_speaker_overlap(event, offset_a, offset_b):
    room = RoomFactory(event=event)
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
        room=room,
        start=base + dt.timedelta(minutes=offset_a[0]),
        end=base + dt.timedelta(minutes=offset_a[1]),
    )
    slot2 = TalkSlotFactory(
        submission=submission2,
        schedule=schedule,
        room=room,
        start=base + dt.timedelta(minutes=offset_b[0]),
        end=base + dt.timedelta(minutes=offset_b[1]),
    )

    with scope(event=event):
        warnings = get_talk_warnings(schedule, slot1, with_speakers=False)
        bulk = get_all_talk_warnings(schedule)

    assert _types(warnings) == ["room_overlap", "speaker"]
    speaker_warning = next(w for w in warnings if w["type"] == "speaker")
    assert "another session" in speaker_warning["message"]
    assert speaker_warning["speaker"]["code"] == speaker.code
    assert {slot: _types(warnings) for slot, warnings in bulk.items()} == {
        slot1: ["room_overlap", "speaker"],
        slot2: ["room_overlap", "speaker"],
    }


def test_schedule_get_all_talk_warnings_filter_updated_reports_only_touched_slots(
    event,
):
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission1 = SubmissionFactory(event=event)
    submission2 = SubmissionFactory(event=event)
    submission1.speakers.add(speaker)
    submission2.speakers.add(speaker)
    start = event.datetime_from
    end = start + dt.timedelta(hours=1)
    with scope(event=event):
        schedule = event.wip_schedule
    stable_slot = TalkSlotFactory(
        submission=submission1, schedule=schedule, room=room, start=start, end=end
    )
    TalkSlot.objects.filter(pk=stable_slot.pk).update(
        updated=tz_now() - dt.timedelta(hours=2)
    )
    touched_slot = TalkSlotFactory(
        submission=submission2,
        schedule=schedule,
        room=RoomFactory(event=event),
        start=start,
        end=end,
    )

    with scope(event=event):
        result = get_all_talk_warnings(
            schedule, filter_updated=tz_now() - dt.timedelta(minutes=5)
        )
        single = get_talk_warnings(schedule, touched_slot, with_speakers=False)

    assert {slot: _types(warnings) for slot, warnings in result.items()} == {
        touched_slot: ["speaker"]
    }
    assert "another session" in result[touched_slot][0]["message"]
    assert _types(single) == ["speaker"]


def test_schedule_get_all_talk_warnings_non_overlapping_is_empty(event):
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission1 = SubmissionFactory(event=event)
    submission2 = SubmissionFactory(event=event)
    submission1.speakers.add(speaker)
    submission2.speakers.add(speaker)
    start = event.datetime_from
    with scope(event=event):
        schedule = event.wip_schedule
    stable_slot = TalkSlotFactory(
        submission=submission1,
        schedule=schedule,
        room=room,
        start=start,
        end=start + dt.timedelta(minutes=30),
    )
    TalkSlot.objects.filter(pk=stable_slot.pk).update(
        updated=tz_now() - dt.timedelta(hours=2)
    )
    TalkSlotFactory(
        submission=submission2,
        schedule=schedule,
        room=room,
        start=start + dt.timedelta(minutes=60),
        end=start + dt.timedelta(minutes=90),
    )

    with scope(event=event):
        assert get_all_talk_warnings(schedule) == {}
        assert (
            get_all_talk_warnings(
                schedule, filter_updated=tz_now() - dt.timedelta(minutes=5)
            )
            == {}
        )
        assert (
            get_all_talk_warnings(
                schedule, filter_updated=tz_now() + dt.timedelta(hours=1)
            )
            == {}
        )


def test_schedule_get_all_talk_warnings_breaks(event):
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

    assert {slot: _types(warnings) for slot, warnings in bulk.items()} == {
        open_slot: ["room_overlap"],
        overlapping_slot: ["room_overlap"],
    }


def test_schedule_get_talk_warnings_room_availability(event):
    room = RoomFactory(event=event, hidden=True)
    avail = AvailabilityFactory(
        event=event,
        room=room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=2),
    )
    late_start = event.datetime_from + dt.timedelta(hours=10)
    with scope(event=event):
        schedule = event.wip_schedule
    late_slot = TalkSlotFactory(
        submission=SubmissionFactory(event=event),
        schedule=schedule,
        room=room,
        start=late_start,
        end=late_start + dt.timedelta(hours=1),
    )
    covered_slot = TalkSlotFactory(
        submission=SubmissionFactory(event=event),
        schedule=schedule,
        room=room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )

    with scope(event=event):
        late = get_talk_warnings(schedule, late_slot, with_speakers=False)
        late_explicit = get_talk_warnings(
            schedule, late_slot, with_speakers=False, room_avails=None
        )
        covered = get_talk_warnings(
            schedule, covered_slot, with_speakers=False, room_avails=[avail]
        )
        bulk = get_all_talk_warnings(schedule)

    assert _types(late) == ["room"]
    assert _types(late_explicit) == ["room"]
    assert covered == []
    assert {slot: _types(warnings) for slot, warnings in bulk.items()} == {
        late_slot: ["room"]
    }


def test_schedule_get_talk_warnings_speaker_availability_only_with_speakers(event):
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
    covered_submission = SubmissionFactory(event=event)
    covered_submission.speakers.add(speaker)
    covered_slot = TalkSlotFactory(
        submission=covered_submission,
        schedule=schedule,
        room=RoomFactory(event=event),
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )

    with scope(event=event):
        with_speakers = get_talk_warnings(schedule, slot, with_speakers=True)
        without_speakers = get_talk_warnings(schedule, slot, with_speakers=False)
        covered = get_talk_warnings(schedule, covered_slot, with_speakers=True)

    assert _types(with_speakers) == ["speaker"]
    assert "not available" in with_speakers[0]["message"]
    assert with_speakers[0]["speaker"]["code"] == speaker.code
    assert without_speakers == []
    assert covered == []


def test_schedule_warnings_counts_unscheduled_and_unconfirmed(event):
    room = RoomFactory(event=event)
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(
        submission=SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED),
        schedule=schedule,
        room=None,
        start=None,
        end=None,
    )
    TalkSlotFactory(
        submission=SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED),
        schedule=schedule,
        room=room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )

    with scope(event=event):
        result = schedule.warnings

    assert result["unscheduled"] == 1
    assert result["unconfirmed"] == 1


@pytest.mark.parametrize(("use_tracks", "expected_count"), ((True, 1), (False, 0)))
def test_schedule_warnings_no_track_only_when_tracks_enabled(
    use_tracks, expected_count
):
    event = EventFactory(feature_flags={"use_tracks": use_tracks})
    TrackFactory(event=event)
    submission = SubmissionFactory(event=event, track=None)
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(submission=submission, schedule=schedule)

    with scope(event=event):
        result = schedule.warnings

    assert len(list(result["no_track"])) == expected_count


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


def test_signup_room_too_small_is_a_per_talk_warning_only():
    event = _signup_event()
    submission, slot = _required_signup_slot(
        event, room_capacity=20, session_capacity=50
    )

    with scope(event=event):
        warnings = get_talk_warnings(event.wip_schedule, slot, with_speakers=False)
        bulk = get_all_talk_warnings(event.wip_schedule)
        release_warnings = compute_signup_warnings(event.wip_schedule)

    assert _types(warnings) == ["signup_room_too_small"]
    assert "20" in warnings[0]["message"]
    assert "50" in warnings[0]["message"]
    (annotated_slot,) = bulk.keys()
    assert _types(bulk[annotated_slot]) == ["signup_room_too_small"]
    # Slots are annotated with ``_annotated_requires_signup`` so the helper
    # can short-circuit without re-querying.
    assert annotated_slot._annotated_requires_signup is True
    assert "signup_room_too_small" not in release_warnings
    assert release_warnings["signup_room_too_large"] == []


def test_signup_overfull_is_a_release_warning_only():
    event = _signup_event()
    submission, slot = _required_signup_slot(event, room_capacity=2, session_capacity=2)
    for _ in range(3):
        AttendeeSignupFactory(submission=submission)

    with scope(event=event):
        editor_warnings = get_talk_warnings(
            event.wip_schedule, slot, with_speakers=False
        )
        release_warnings = compute_signup_warnings(event.wip_schedule)

    assert "signup_overfull" not in _types(editor_warnings)
    assert [
        (entry["submission"], entry["signup_count"])
        for entry in release_warnings["signup_overfull"]
    ] == [(submission, 3)]


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


@pytest.mark.parametrize("is_visible", (True, False))
def test_compute_signup_warnings_room_too_large(is_visible):
    event = _signup_event()
    submission, slot = _required_signup_slot(
        event, room_capacity=100, session_capacity=40, is_visible=is_visible
    )

    with scope(event=event):
        warnings = compute_signup_warnings(event.wip_schedule)

    assert [
        (entry["submission"], entry["current_capacity"], entry["room_capacity"])
        for entry in warnings["signup_room_too_large"]
    ] == [(submission, 40, 100)]
    assert warnings["signup_overfull"] == []


@pytest.mark.parametrize(
    ("room_capacity", "session_capacity", "expected_count"),
    ((None, None, 1), (None, 50, 0), (20, None, 0)),
    ids=["both_unset", "session_capacity_set", "room_capacity_set"],
)
def test_compute_signup_warnings_no_capacity_flags_only_fully_unset_sessions(
    room_capacity, session_capacity, expected_count
):
    event = _signup_event()
    submission, slot = _required_signup_slot(
        event, room_capacity=room_capacity, session_capacity=session_capacity
    )

    with scope(event=event):
        warnings = compute_signup_warnings(event.wip_schedule)

    assert [
        (entry["submission"], entry["slot"]) for entry in warnings["signup_no_capacity"]
    ] == [(submission, slot)] * expected_count


@pytest.mark.parametrize("room_capacity", (None, 10))
def test_compute_signup_warnings_ignores_signup_not_required(room_capacity):
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


def test_compute_signup_warnings_dropped_session_only_with_attendees():
    event = _signup_event()
    submission, _slot = _required_signup_slot(event, room_capacity=50)
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        wip = event.wip_schedule

        assert compute_signup_warnings(wip)["signup_dropped_with_attendees"] == []

        wip.talks.update(room=None, start=None, end=None, is_visible=False)
        assert compute_signup_warnings(wip)["signup_dropped_with_attendees"] == []

        AttendeeSignupFactory(submission=submission)
        dropped = compute_signup_warnings(wip)["signup_dropped_with_attendees"]

    assert [(entry["submission"], entry["signup_count"]) for entry in dropped] == [
        (submission, 1)
    ]


def test_compute_signup_warnings_dropped_ignores_visibility_but_sees_cancellation():
    event = _signup_event()
    submission, _slot = _required_signup_slot(event, room_capacity=50)
    AttendeeSignupFactory(submission=submission)
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        wip = event.wip_schedule

        wip.talks.update(is_visible=False)
        assert compute_signup_warnings(wip)["signup_dropped_with_attendees"] == []

        submission.state = SubmissionStates.CANCELED
        submission.save()
        dropped = compute_signup_warnings(wip)["signup_dropped_with_attendees"]

    assert [(entry["submission"], entry["signup_count"]) for entry in dropped] == [
        (submission, 1)
    ]


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


def test_compute_signup_warnings_current_capacity_zero_is_not_treated_as_unset():
    event = _signup_event()
    submission, _slot = _required_signup_slot(
        event, room_capacity=20, session_capacity=None
    )
    # The model validator floors capacity at 1 for new input, but stored
    # rows might end up with 0 from data migrations or admin tooling.
    # Bypass the validator with an UPDATE.
    Submission.objects.filter(pk=submission.pk).update(attendee_signup_capacity=0)

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


def test_overbooked_slots_for_room_ignores_other_rooms_and_unscheduled_slots():
    event = _signup_event()
    sub_type = event.cfp.default_type
    sub_type.attendee_signup_required = True
    sub_type.save()
    room = RoomFactory(event=event, capacity=1)
    unscheduled = SubmissionFactory(
        event=event, state=SubmissionStates.CONFIRMED, submission_type=sub_type
    )
    TalkSlotFactory(
        submission=unscheduled,
        schedule=event.wip_schedule,
        room=room,
        start=None,
        end=None,
    )
    other_room = RoomFactory(event=event, capacity=1)
    elsewhere = SubmissionFactory(
        event=event, state=SubmissionStates.CONFIRMED, submission_type=sub_type
    )
    TalkSlotFactory(
        submission=elsewhere,
        schedule=event.wip_schedule,
        room=other_room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )
    for _ in range(5):
        AttendeeSignupFactory(submission=unscheduled)
        AttendeeSignupFactory(submission=elsewhere)

    with scope(event=event):
        assert list(overbooked_slots_for_room(room)) == []
