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


def test_talkslot_str():
    slot = TalkSlotFactory()

    result = str(slot)

    assert result == (
        f"TalkSlot(event={slot.schedule.event.slug}, "
        f"submission={slot.submission.title}, "
        f"schedule={slot.schedule.version})"
    )


def test_talkslot_str_without_submission():
    schedule = ScheduleFactory()
    slot = TalkSlotFactory(submission=None, schedule=schedule, room=None)

    result = str(slot)

    assert result == (
        f"TalkSlot(event={schedule.event.slug}, "
        f"submission=None, "
        f"schedule={slot.schedule.version})"
    )


def test_talkslot_event_from_submission():
    slot = TalkSlotFactory()

    assert slot.event == slot.submission.event


def test_talkslot_event_from_schedule_when_no_submission():
    schedule = ScheduleFactory()
    slot = TalkSlotFactory(submission=None, schedule=schedule, room=None)

    assert slot.event == schedule.event


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
    """Duration is computed from start/end when both are set, falls back to
    submission duration, or returns None for non-submission slots without times."""
    now = dt.datetime(2024, 1, 1, 10, 0, tzinfo=dt.UTC)
    start = now if has_start else None
    end = now + dt.timedelta(minutes=42) if has_end else None
    submission = SubmissionFactory() if has_submission else None
    slot = TalkSlot(start=start, end=end, submission=submission)

    result = slot.duration

    if expected == "computed":
        assert result == 42
    elif expected == "submission":
        assert result == submission.get_duration()
    else:
        assert result is None


def test_talkslot_export_duration():
    now = dt.datetime(2024, 1, 1, 10, 0, tzinfo=dt.UTC)
    slot = TalkSlot(start=now, end=now + dt.timedelta(hours=1, minutes=30))

    assert slot.export_duration == "01:30"


def test_talkslot_pentabarf_export_duration():
    now = dt.datetime(2024, 1, 1, 10, 0, tzinfo=dt.UTC)
    slot = TalkSlot(start=now, end=now + dt.timedelta(hours=2, minutes=15))

    assert slot.pentabarf_export_duration == "021500"


def test_talkslot_local_start():
    slot = TalkSlotFactory()

    result = slot.local_start

    assert result == slot.start.astimezone(slot.event.tz)


def test_talkslot_local_start_none_when_no_start():
    schedule = ScheduleFactory()
    slot = TalkSlot(start=None, schedule=schedule)

    assert slot.local_start is None


def test_talkslot_real_end_from_end():
    slot = TalkSlotFactory()

    assert slot.real_end == slot.end


def test_talkslot_real_end_computed_when_no_end():
    slot = TalkSlotFactory()
    start = slot.start
    slot.end = None

    result = slot.real_end

    assert result == start + dt.timedelta(minutes=slot.duration)


def test_talkslot_real_end_none_when_no_start_or_end():
    schedule = ScheduleFactory()
    slot = TalkSlot(start=None, end=None, schedule=schedule)

    assert slot.real_end is None


def test_talkslot_local_end():
    slot = TalkSlotFactory()

    result = slot.local_end

    assert result == slot.real_end.astimezone(slot.event.tz)


def test_talkslot_local_end_none_when_no_real_end():
    schedule = ScheduleFactory()
    slot = TalkSlot(start=None, end=None, schedule=schedule)

    assert slot.local_end is None


def test_talkslot_as_availability():
    slot = TalkSlotFactory()

    avail = slot.as_availability

    assert avail.start == slot.start
    assert avail.end == slot.real_end


def test_talkslot_is_same_slot_true():
    room = RoomFactory()
    start = dt.datetime(2024, 1, 1, 10, 0, tzinfo=dt.UTC)
    slot_a = TalkSlot(room=room, start=start)
    slot_b = TalkSlot(room=room, start=start)

    assert slot_a.is_same_slot(slot_b) is True


def test_talkslot_is_same_slot_different_room():
    room_a = RoomFactory()
    room_b = RoomFactory(event=room_a.event)
    start = dt.datetime(2024, 1, 1, 10, 0, tzinfo=dt.UTC)
    slot_a = TalkSlot(room=room_a, start=start)
    slot_b = TalkSlot(room=room_b, start=start)

    assert slot_a.is_same_slot(slot_b) is False


def test_talkslot_is_same_slot_different_start():
    start_a = dt.datetime(2024, 1, 1, 10, 0, tzinfo=dt.UTC)
    start_b = dt.datetime(2024, 1, 1, 11, 0, tzinfo=dt.UTC)
    slot_a = TalkSlot(start=start_a)
    slot_b = TalkSlot(start=start_b)

    assert slot_a.is_same_slot(slot_b) is False


def test_talkslot_id_suffix_empty_when_feature_disabled():
    slot = TalkSlotFactory()

    assert slot.id_suffix == ""


def test_talkslot_id_suffix_empty_when_single_slot():
    """Even with feature enabled, a single slot gets no suffix."""
    slot = TalkSlotFactory(
        submission__event__feature_flags={"present_multiple_times": True}
    )

    assert slot.id_suffix == ""


def test_talkslot_id_suffix_with_multiple_slots():
    slot1 = TalkSlotFactory(
        submission__event__feature_flags={"present_multiple_times": True}
    )

    slot2 = TalkSlotFactory(
        submission=slot1.submission,
        schedule=slot1.schedule,
        start=slot1.start + dt.timedelta(hours=2),
        end=slot1.end + dt.timedelta(hours=2),
    )
    assert slot1.id_suffix == "-0"
    assert slot2.id_suffix == "-1"


def test_talkslot_frab_slug_basic():
    submission = SubmissionFactory(title="my talk")
    slot = TalkSlotFactory(submission=submission)

    result = slot.frab_slug

    assert result == f"{slot.event.slug}-{submission.pk}-my-talk"


def test_talkslot_frab_slug_normalizes_unicode():
    submission = SubmissionFactory(title="Über Café")
    slot = TalkSlotFactory(submission=submission)

    result = slot.frab_slug

    assert result == f"{slot.event.slug}-{submission.pk}-uber-cafe"


def test_talkslot_frab_slug_empty_title_after_normalization():
    submission = SubmissionFactory(title="日本語")
    slot = TalkSlotFactory(submission=submission)

    result = slot.frab_slug

    assert result == f"{slot.event.slug}-{submission.pk}"


def test_talkslot_uuid_is_uuid5():
    slot = TalkSlotFactory()

    result = slot.uuid

    assert isinstance(result, uuid.UUID)
    assert result.version == 5


def test_talkslot_uuid_is_stable():
    slot = TalkSlotFactory()

    uuid1 = slot.uuid
    del slot.__dict__["uuid"]
    uuid2 = slot.uuid

    assert uuid1 == uuid2


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
    """``None`` is the common annotation value for non-signup sessions, so
    the property must short-circuit on ``hasattr`` (not truthiness),
    otherwise annotated querysets re-issue per-row queries."""
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
    """Without an annotation, the slot returns whatever the submission says.

    The submission uses its own capacity override here so the test stays
    independent of which schedule the slot lives on.
    """
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
    slot = TalkSlot.objects.get(pk=slot.pk)
    assert slot.signup_status == "full"
