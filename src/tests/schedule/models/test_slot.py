# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import uuid

import pytest
from django_scopes import scope

from pretalx.schedule.models.slot import TalkSlot
from tests.factories import (
    AttendeeSignupFactory,
    EventFactory,
    RoomFactory,
    ScheduleFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TalkSlotFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_talkslot_event_from_submission_or_schedule():
    talk = TalkSlotFactory()
    schedule = ScheduleFactory()
    break_slot = TalkSlotFactory(submission=None, schedule=schedule, room=None)

    assert talk.event == talk.submission.event
    assert break_slot.event == schedule.event


@pytest.mark.parametrize(
    ("has_start", "has_end", "has_submission", "expected"),
    (
        (True, True, True, "computed"),
        (True, True, False, "computed"),
        (True, False, True, "submission"),
        (False, True, True, "submission"),
        (False, False, True, "submission"),
        (True, False, False, None),
        (False, True, False, None),
        (False, False, False, None),
    ),
)
def test_talkslot_duration(has_start, has_end, has_submission, expected):
    now = dt.datetime(2024, 1, 1, 10, 0, tzinfo=dt.UTC)
    start = now if has_start else None
    end = now + dt.timedelta(minutes=42) if has_end else None
    submission = SubmissionFactory() if has_submission else None
    slot = TalkSlot(start=start, end=end, submission=submission)

    result = slot.duration

    match expected:
        case "computed":
            assert result == 42
        case "submission":
            assert result == submission.get_duration()
        case _:
            assert result is None


def test_talkslot_export_durations():
    now = dt.datetime(2024, 1, 1, 10, 0, tzinfo=dt.UTC)
    slot = TalkSlot(start=now, end=now + dt.timedelta(hours=1, minutes=30))

    assert (slot.export_duration, slot.pentabarf_export_duration) == ("01:30", "013000")


def test_talkslot_time_properties():
    slot = TalkSlotFactory()
    tz = slot.event.tz

    assert slot.local_start == slot.start.astimezone(tz)
    assert slot.real_end == slot.end
    assert slot.local_end == slot.end.astimezone(tz)
    assert (slot.as_availability.start, slot.as_availability.end) == (
        slot.start,
        slot.end,
    )

    slot.end = None
    del slot.__dict__["real_end"]

    assert slot.real_end == slot.start + dt.timedelta(minutes=slot.duration)


def test_talkslot_time_properties_none_without_start():
    slot = TalkSlot(start=None, end=None, schedule=ScheduleFactory())

    assert (slot.local_start, slot.real_end, slot.local_end) == (None, None, None)


def test_talkslot_is_same_slot_compares_room_and_start():
    room_a = RoomFactory()
    room_b = RoomFactory(event=room_a.event)
    start = dt.datetime(2024, 1, 1, 10, 0, tzinfo=dt.UTC)
    slot = TalkSlot(room=room_a, start=start)

    assert slot.is_same_slot(TalkSlot(room=room_a, start=start)) is True
    assert slot.is_same_slot(TalkSlot(room=room_b, start=start)) is False
    assert (
        slot.is_same_slot(TalkSlot(room=room_a, start=start + dt.timedelta(hours=1)))
        is False
    )


def test_talkslot_id_suffix_numbers_multiple_slots_when_enabled():
    disabled = TalkSlotFactory()
    slot1 = TalkSlotFactory(
        submission__event__feature_flags={"present_multiple_times": True}
    )
    single = slot1.id_suffix
    slot2 = TalkSlotFactory(
        submission=slot1.submission,
        schedule=slot1.schedule,
        start=slot1.start + dt.timedelta(hours=2),
        end=slot1.end + dt.timedelta(hours=2),
    )
    del slot1.__dict__["id_suffix"]

    assert (disabled.id_suffix, single, slot1.id_suffix, slot2.id_suffix) == (
        "",
        "",
        "-0",
        "-1",
    )


@pytest.mark.parametrize(
    ("title", "suffix"),
    (("my talk", "-my-talk"), ("Über Café", "-uber-cafe"), ("日本語", "")),
    ids=["basic", "normalizes_unicode", "empty_after_normalization"],
)
def test_talkslot_frab_slug(title, suffix):
    submission = SubmissionFactory(title=title)
    slot = TalkSlotFactory(submission=submission)

    assert slot.frab_slug == f"{slot.event.slug}-{submission.pk}{suffix}"


def test_talkslot_uuid_is_stable_uuid5():
    slot = TalkSlotFactory()

    first = slot.uuid
    del slot.__dict__["uuid"]

    assert isinstance(first, uuid.UUID)
    assert first.version == 5
    assert slot.uuid == first


def test_talkslot_ordering_by_start():
    submission = SubmissionFactory()
    event = submission.event
    early = dt.datetime(2024, 1, 1, 9, 0, tzinfo=dt.UTC)
    late = dt.datetime(2024, 1, 1, 14, 0, tzinfo=dt.UTC)
    slot_late = TalkSlotFactory(
        submission=submission, start=late, end=late + dt.timedelta(hours=1)
    )
    slot_early = TalkSlotFactory(
        submission=submission, start=early, end=early + dt.timedelta(hours=1)
    )

    slots = list(event.wip_schedule.talks.all())

    assert slots == [slot_early, slot_late]


@pytest.mark.parametrize("annotated_value", ("full", None))
def test_talkslot_signup_status_short_circuits_on_annotation(
    django_assert_num_queries, annotated_value
):
    event = EventFactory(feature_flags={"attendee_signup": True})
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    submission = SubmissionFactory(event=event, submission_type=sub_type)
    with scope(event=event):
        slot = TalkSlotFactory(submission=submission, schedule=event.wip_schedule)
        slot = TalkSlot.objects.get(pk=slot.pk)
    slot._annotated_signup_status = annotated_value

    with django_assert_num_queries(0):
        assert slot.signup_status == annotated_value


def test_talkslot_signup_status_none_for_break_slot():
    schedule = ScheduleFactory()
    slot = TalkSlotFactory(submission=None, schedule=schedule, room=None)

    assert slot.signup_status is None


def test_talkslot_signup_status_falls_through_to_submission():
    event = EventFactory(feature_flags={"attendee_signup": True})
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    submission = SubmissionFactory(
        event=event, submission_type=sub_type, attendee_signup_capacity=1
    )
    with scope(event=event):
        schedule = event.wip_schedule
        slot = TalkSlotFactory(submission=submission, schedule=schedule)
        AttendeeSignupFactory(submission=submission)

    # Force fresh property
    slot = TalkSlot.objects.select_related(
        "submission__event", "submission__submission_type"
    ).get(pk=slot.pk)
    assert slot.signup_status == "full"
