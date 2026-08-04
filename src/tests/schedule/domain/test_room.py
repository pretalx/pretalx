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

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_delete_room_removes_unused_room(event):
    room = RoomFactory(event=event)

    delete_room(room)

    assert not Room.objects.filter(pk=room.pk).exists()


def test_delete_room_raises_protected_error_when_referenced():
    slot = TalkSlotFactory()
    room = slot.room

    with pytest.raises(ProtectedError):
        delete_room(room)

    assert Room.objects.filter(pk=room.pk).exists()


def test_active_schedule_pks_without_released_schedule(event):
    with scope(event=event):
        assert active_schedule_pks(event) == [event.wip_schedule.pk]


def test_active_schedule_pks_with_released_schedule(event):
    released = ScheduleFactory(event=event, version="v1")

    with scope(event=event):
        result = active_schedule_pks(event)

    assert set(result) == {event.wip_schedule.pk, released.pk}


def test_room_is_in_use_only_for_current_or_wip_slots(event):
    old_room = RoomFactory(event=event)
    wip_room = TalkSlotFactory(submission__event=event).room
    old_schedule = ScheduleFactory(event=event, version="v0", published=None)
    TalkSlotFactory(submission=None, room=old_room, schedule=old_schedule)

    with scope(event=event):
        assert room_is_in_use(wip_room) is True
        assert room_is_in_use(old_room) is False


def test_annotate_room_usage_matches_predicates(event):
    unused_room = RoomFactory(event=event)
    historic_room = RoomFactory(event=event)
    historic_schedule = ScheduleFactory(event=event, version="v0", published=None)
    TalkSlotFactory(submission=None, room=historic_room, schedule=historic_schedule)
    current_room = TalkSlotFactory(submission__event=event).room

    with scope(event=event):
        rooms = {
            room.pk: room
            for room in annotate_room_usage(event.rooms.all(), event=event)
        }

    assert (rooms[unused_room.pk].is_deletable, rooms[unused_room.pk].is_in_use) == (
        True,
        False,
    )
    assert (
        rooms[historic_room.pk].is_deletable,
        rooms[historic_room.pk].is_in_use,
    ) == (False, False)
    assert (rooms[current_room.pk].is_deletable, rooms[current_room.pk].is_in_use) == (
        False,
        True,
    )


def test_hide_room_sets_flag_and_logs(event):
    user = UserFactory()
    room = RoomFactory(event=event)

    with scope(event=event):
        hide_room(room, log_kwargs={"person": user, "orga": True})

    room.refresh_from_db()
    assert room.hidden is True
    log = ActivityLog.objects.get(action_type="pretalx.room.hide")
    assert log.content_object == room
    assert log.person == user


def test_hide_room_refuses_room_with_scheduled_sessions(event):
    room = TalkSlotFactory(submission__event=event).room

    with scope(event=event), pytest.raises(ValidationError):
        hide_room(room)

    room.refresh_from_db()
    assert room.hidden is False
    assert not ActivityLog.objects.filter(action_type="pretalx.room.hide").exists()


def test_unhide_room_clears_flag_and_logs(event):
    user = UserFactory()
    room = RoomFactory(event=event, hidden=True, position=3)

    with scope(event=event):
        unhide_room(room, log_kwargs={"person": user, "orga": True})

    room.refresh_from_db()
    assert room.hidden is False
    assert room.position == 3
    log = ActivityLog.objects.get(action_type="pretalx.room.unhide")
    assert log.content_object == room
