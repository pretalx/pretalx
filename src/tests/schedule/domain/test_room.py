# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.db.models.deletion import ProtectedError

from pretalx.schedule.domain.room import delete_room
from pretalx.schedule.models import Room
from tests.factories import RoomFactory, TalkSlotFactory

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
