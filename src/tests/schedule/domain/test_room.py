# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django_scopes import scope

from pretalx.common.models import ActivityLog
from pretalx.schedule.domain.room import (
    active_schedule_pks,
    annotate_room_usage,
    delete_room,
    hide_room,
    room_is_in_use,
    unhide_room,
)
from pretalx.schedule.models import Room
from tests.factories import RoomFactory, ScheduleFactory, TalkSlotFactory, UserFactory
from tests.utils import refresh

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_delete_room_protects_referenced_rooms(event):
    unused_room = RoomFactory(event=event)
    used_room = TalkSlotFactory(submission__event=event).room

    delete_room(unused_room)
    with pytest.raises(ProtectedError):
        delete_room(used_room)

    assert list(Room.objects.filter(event=event)) == [used_room]


def test_active_schedule_pks_adds_released_schedule(event):
    with scope(event=event):
        assert active_schedule_pks(event) == [event.wip_schedule.pk]

    released = ScheduleFactory(event=event, version="v1")
    event = refresh(event)

    with scope(event=event):
        assert active_schedule_pks(event) == [event.wip_schedule.pk, released.pk]


def test_room_usage_only_for_current_or_wip_slots(event):
    unused_room = RoomFactory(event=event)
    historic_room = RoomFactory(event=event)
    historic_schedule = ScheduleFactory(event=event, version="v0", published=None)
    TalkSlotFactory(submission=None, room=historic_room, schedule=historic_schedule)
    current_room = TalkSlotFactory(submission__event=event).room

    with scope(event=event):
        in_use = [room_is_in_use(r) for r in (unused_room, historic_room, current_room)]
        annotated = {
            room.pk: (room.is_deletable, room.is_in_use)
            for room in annotate_room_usage(event.rooms.all(), event=event)
        }

    assert in_use == [False, False, True]
    assert annotated == {
        unused_room.pk: (True, False),
        historic_room.pk: (False, False),
        current_room.pk: (False, True),
    }


def test_hide_and_unhide_room(event):
    user = UserFactory()
    room = RoomFactory(event=event, position=3)
    used_room = TalkSlotFactory(submission__event=event).room

    with scope(event=event):
        hide_room(room, log_kwargs={"person": user, "orga": True})
        hidden = room.hidden
        unhide_room(room, log_kwargs={"person": user, "orga": True})
        with pytest.raises(ValidationError):
            hide_room(used_room)

    room.refresh_from_db()
    used_room.refresh_from_db()
    assert (hidden, room.hidden, room.position) == (True, False, 3)
    assert used_room.hidden is False
    logs = ActivityLog.objects.select_related("person").prefetch_related(
        "content_object"
    )
    assert [
        (log.action_type, log.content_object, log.person) for log in logs.order_by("pk")
    ] == [("pretalx.room.hide", room, user), ("pretalx.room.unhide", room, user)]
