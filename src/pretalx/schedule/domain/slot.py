# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

DEFAULT_SLOT_MINUTES = 30


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
