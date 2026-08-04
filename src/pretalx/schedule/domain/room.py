# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Q

from pretalx.schedule.models import TalkSlot
from pretalx.schedule.models.room import ROOM_IN_USE_ERROR

__all__ = [
    "ROOM_IN_USE_ERROR",
    "active_schedule_pks",
    "annotate_room_usage",
    "delete_room",
    "hide_room",
    "room_is_in_use",
    "rooms_for_schedule",
    "unhide_room",
]


def delete_room(room, *, log_kwargs=None):
    """Delete ``room`` together with the activity log entries pointing at it.

    Raises ``django.db.models.deletion.ProtectedError`` if the room is still
    referenced by a ``TalkSlot``; callers translate that into a user-facing
    error.
    """
    with transaction.atomic():
        room.logged_actions().delete()
        room.delete(log_kwargs=log_kwargs or {})


def active_schedule_pks(event):
    pks = [event.wip_schedule.pk]
    if current_schedule := event.current_schedule:
        pks.append(current_schedule.pk)
    return pks


def room_is_in_use(room) -> bool:
    """True if the current or the WIP schedule contains a slot in ``room``."""
    return room.talks.filter(schedule_id__in=active_schedule_pks(room.event)).exists()


def annotate_room_usage(queryset, event):
    slots = TalkSlot.objects.filter(room_id=OuterRef("pk"))
    return queryset.annotate(
        has_slots=Exists(slots),
        has_scheduled_slots=Exists(
            slots.filter(schedule_id__in=active_schedule_pks(event))
        ),
    )


def rooms_for_schedule(schedule):
    return schedule.event.rooms.filter(
        Q(hidden=False) | Q(talks__schedule=schedule)
    ).distinct()


def hide_room(room, *, log_kwargs=None):
    if room.is_in_use:
        raise ValidationError(ROOM_IN_USE_ERROR)
    room.hidden = True
    room.save(update_fields=["hidden", "updated"])
    room.log_action(".hide", **(log_kwargs or {}))


def unhide_room(room, *, log_kwargs=None):
    room.hidden = False
    room.save(update_fields=["hidden", "updated"])
    room.log_action(".unhide", **(log_kwargs or {}))
