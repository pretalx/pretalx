# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest

from pretalx.schedule.domain.slot import (
    copy_slot,
    create_slot,
    move_slot,
    unschedule_slot,
)
from pretalx.schedule.models import TalkSlot
from tests.factories import (
    RoomFactory,
    ScheduleFactory,
    SubmissionFactory,
    TalkSlotFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_create_slot_resolves_end_and_slot_type(event):
    schedule = event.wip_schedule
    room = RoomFactory(event=event)
    start = event.datetime_from
    minutes = dt.timedelta(minutes=1)

    with_duration = create_slot(
        schedule=schedule,
        room=room,
        slot_type="break",
        start=start,
        duration=45,
        description="Coffee",
    )
    explicit_end = create_slot(
        schedule=schedule,
        slot_type="blocker",
        start=start,
        end=start + 120 * minutes,
        duration=999,
    )
    invalid_type = create_slot(schedule=schedule, slot_type="nonsense", start=start)
    default = create_slot(schedule=schedule, slot_type="break", start=start)

    assert (with_duration.submission, with_duration.room, with_duration.start) == (
        None,
        room,
        start,
    )
    assert str(with_duration.description) == "Coffee"
    assert [
        (slot.slot_type, (slot.end - start) / minutes)
        for slot in (with_duration, explicit_end, invalid_type, default)
    ] == [("break", 45), ("blocker", 120), ("break", 30), ("break", 30)]
    assert list(schedule.talks.order_by("pk")) == [
        with_duration,
        explicit_end,
        invalid_type,
        default,
    ]


def test_move_slot_resolves_end_from_arguments_then_submission(event):
    room = RoomFactory(event=event)
    slot = TalkSlotFactory(
        submission=SubmissionFactory(event=event, duration=45), start=None, end=None
    )
    start = event.datetime_from
    explicit_end = start + dt.timedelta(hours=3)

    ends = [
        move_slot(slot, start).end,
        move_slot(slot, start, duration=90).end,
        move_slot(slot, start, end=explicit_end, duration=90).end,
        move_slot(slot, start, room=room).end,
    ]

    assert ends == [
        start + dt.timedelta(minutes=45),
        start + dt.timedelta(minutes=90),
        explicit_end,
        start + dt.timedelta(minutes=45),
    ]
    assert list(
        TalkSlot.objects.filter(pk=slot.pk).values_list("start", "room_id")
    ) == [(start, room.pk)]


def test_move_slot_without_submission_keeps_duration_or_uses_default(event):
    room = RoomFactory(event=event)
    slot = TalkSlotFactory(
        schedule=event.wip_schedule, submission=None, room=room, start=None, end=None
    )
    start = event.datetime_from

    default_end = move_slot(slot, start).end
    slot.end = start + dt.timedelta(minutes=20)
    kept_end = move_slot(slot, start + dt.timedelta(hours=2)).end

    assert default_end == start + dt.timedelta(minutes=30)
    assert kept_end == start + dt.timedelta(hours=2, minutes=20)
    assert TalkSlot.objects.get(pk=slot.pk).end == kept_end


def test_unschedule_slot_clears_fields(event):
    slot = TalkSlotFactory(submission=SubmissionFactory(event=event))

    unschedule_slot(slot)

    assert list(TalkSlot.objects.filter(pk=slot.pk).values("start", "end", "room")) == [
        {"start": None, "end": None, "room": None}
    ]


def test_copy_slot_clones_fields_into_schedule():
    slot = TalkSlotFactory()
    new_schedule = ScheduleFactory(event=slot.schedule.event)

    unsaved = copy_slot(slot, schedule=new_schedule, save=False)
    saved = copy_slot(slot, schedule=new_schedule)

    assert unsaved.pk is None
    assert saved.pk not in (None, slot.pk)
    for copy in (unsaved, saved):
        assert (
            copy.schedule,
            copy.submission,
            copy.room,
            copy.start,
            copy.end,
            copy.is_visible,
        ) == (
            new_schedule,
            slot.submission,
            slot.room,
            slot.start,
            slot.end,
            slot.is_visible,
        )
    assert list(new_schedule.talks.all()) == [saved]
