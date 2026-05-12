# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

from pretalx.schedule.enums import SlotType
from pretalx.schedule.models import TalkSlot

DEFAULT_SLOT_MINUTES = 30


def create_slot(
    *,
    schedule,
    room=None,
    slot_type=SlotType.BREAK,
    start,
    end=None,
    duration=None,
    description=None,
):
    """Create a non-submission slot (break or blocker) on ``schedule``."""
    if slot_type not in SlotType.values:
        slot_type = SlotType.BREAK
    if end is None:
        minutes = duration if duration is not None else DEFAULT_SLOT_MINUTES
        end = start + dt.timedelta(minutes=minutes)
    return schedule.talks.create(
        room=room, description=description, start=start, end=end, slot_type=slot_type
    )


def move_slot(slot, start, *, room=None, end=None, duration=None):
    """Place ``slot`` at ``start`` (and consequently at ``end``).

    ``end`` is determined in this priority order: an explicit ``end``
    argument, then ``duration`` in minutes, then the slot's submission
    duration, then the slot's own current duration, finally a default
    fallback for slots without a submission.
    """
    if end is None:
        if duration is not None:
            minutes = duration
        elif slot.submission:
            minutes = slot.submission.get_duration()
        else:
            minutes = slot.duration or DEFAULT_SLOT_MINUTES
        end = start + dt.timedelta(minutes=minutes)
    slot.start = start
    slot.end = end
    if room is not None:
        slot.room = room
    slot.save(update_fields=["start", "end", "room", "updated"])
    return slot


def unschedule_slot(slot):
    """Drop the slot from the schedule (clear start, end, and room)."""
    slot.start = None
    slot.end = None
    slot.room = None
    slot.save(update_fields=["start", "end", "room", "updated"])
    return slot


def copy_slot(slot, *, schedule, save=True):
    """Create a new slot in ``schedule`` cloning every field of ``slot``."""
    new_slot = TalkSlot(schedule=schedule)
    for field in slot._meta.fields:
        if field.name in ("id", "schedule"):
            continue
        setattr(new_slot, field.name, getattr(slot, field.name))
    if save:
        new_slot.save()
    return new_slot
