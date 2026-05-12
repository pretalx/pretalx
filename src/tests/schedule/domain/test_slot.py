# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest

from pretalx.schedule.domain.slot import (
    DEFAULT_SLOT_MINUTES,
    copy_slot,
    create_slot,
    move_slot,
    unschedule_slot,
)
from tests.factories import (
    RoomFactory,
    ScheduleFactory,
    SubmissionFactory,
    TalkSlotFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_create_slot_with_duration(event):
    room = RoomFactory(event=event)
    start = event.datetime_from

    slot = create_slot(
        schedule=event.wip_schedule,
        room=room,
        slot_type="break",
        start=start,
        duration=45,
        description="Coffee",
    )

    assert slot.pk is not None
    assert slot.submission is None
    assert slot.room == room
    assert slot.slot_type == "break"
    assert slot.start == start
    assert slot.end == start + dt.timedelta(minutes=45)
    assert str(slot.description) == "Coffee"


def test_create_slot_explicit_end_wins(event):
    start = event.datetime_from
    end = start + dt.timedelta(hours=2)

    slot = create_slot(
        schedule=event.wip_schedule,
        slot_type="blocker",
        start=start,
        end=end,
        duration=999,
    )

    assert slot.end == end
    assert slot.slot_type == "blocker"


def test_create_slot_invalid_slot_type_falls_back_to_break(event):
    slot = create_slot(
        schedule=event.wip_schedule, slot_type="nonsense", start=event.datetime_from
    )

    assert slot.slot_type == "break"
    assert slot.end == event.datetime_from + dt.timedelta(minutes=DEFAULT_SLOT_MINUTES)


def test_create_slot_without_duration_uses_default(event):
    slot = create_slot(
        schedule=event.wip_schedule, slot_type="break", start=event.datetime_from
    )

    assert slot.end == event.datetime_from + dt.timedelta(minutes=DEFAULT_SLOT_MINUTES)


def test_move_slot_uses_submission_duration(event):
    submission = SubmissionFactory(event=event, duration=45)
    slot = TalkSlotFactory(submission=submission, start=None, end=None)
    new_start = event.datetime_from

    move_slot(slot, new_start)

    slot.refresh_from_db()
    assert slot.start == new_start
    assert slot.end == new_start + dt.timedelta(minutes=45)


def test_move_slot_explicit_duration_overrides_submission(event):
    submission = SubmissionFactory(event=event, duration=45)
    slot = TalkSlotFactory(submission=submission)
    new_start = event.datetime_from

    move_slot(slot, new_start, duration=90)

    assert slot.end == new_start + dt.timedelta(minutes=90)


def test_move_slot_explicit_end_wins_over_duration(event):
    submission = SubmissionFactory(event=event, duration=45)
    slot = TalkSlotFactory(submission=submission)
    new_start = event.datetime_from
    new_end = new_start + dt.timedelta(hours=3)

    move_slot(slot, new_start, end=new_end, duration=90)

    assert slot.end == new_end


def test_move_slot_assigns_room(event):
    room = RoomFactory(event=event)
    submission = SubmissionFactory(event=event)
    slot = TalkSlotFactory(submission=submission, room=None)

    move_slot(slot, event.datetime_from, room=room)

    slot.refresh_from_db()
    assert slot.room == room


def test_move_slot_without_submission_uses_default(event):
    room = RoomFactory(event=event)
    slot = TalkSlotFactory(
        schedule=event.wip_schedule, submission=None, room=room, start=None, end=None
    )

    move_slot(slot, event.datetime_from)

    slot.refresh_from_db()
    assert slot.end == event.datetime_from + dt.timedelta(minutes=DEFAULT_SLOT_MINUTES)


def test_move_slot_without_submission_uses_existing_duration(event):
    room = RoomFactory(event=event)
    existing_start = event.datetime_from
    slot = TalkSlotFactory(
        schedule=event.wip_schedule,
        submission=None,
        room=room,
        start=existing_start,
        end=existing_start + dt.timedelta(minutes=20),
    )

    new_start = existing_start + dt.timedelta(hours=2)
    move_slot(slot, new_start)

    assert slot.end == new_start + dt.timedelta(minutes=20)


def test_unschedule_slot_clears_fields(event):
    room = RoomFactory(event=event)
    submission = SubmissionFactory(event=event)
    slot = TalkSlotFactory(submission=submission, room=room)

    unschedule_slot(slot)

    slot.refresh_from_db()
    assert slot.start is None
    assert slot.end is None
    assert slot.room is None


def test_copy_slot():
    slot = TalkSlotFactory()
    new_schedule = ScheduleFactory(event=slot.schedule.event)

    new_slot = copy_slot(slot, schedule=new_schedule)

    assert new_slot.pk is not None
    assert new_slot.pk != slot.pk
    assert new_slot.schedule == new_schedule
    assert new_slot.submission == slot.submission
    assert new_slot.room == slot.room
    assert new_slot.start == slot.start
    assert new_slot.end == slot.end
    assert new_slot.is_visible == slot.is_visible


def test_copy_slot_without_save():
    slot = TalkSlotFactory()
    new_schedule = ScheduleFactory(event=slot.schedule.event)

    new_slot = copy_slot(slot, schedule=new_schedule, save=False)

    assert new_slot.pk is None
    assert new_slot.schedule == new_schedule
    assert new_slot.submission == slot.submission
