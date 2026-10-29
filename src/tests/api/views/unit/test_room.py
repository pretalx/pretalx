# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from rest_framework import exceptions

from pretalx.api.views.room import RoomViewSet
from tests.factories import AvailabilityFactory, RoomFactory, TalkSlotFactory
from tests.utils import make_api_request, make_orga_user, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_roomviewset_get_queryset_hides_hidden_rooms_from_public(
    django_assert_num_queries,
):
    room = RoomFactory()
    event = room.event
    hidden = RoomFactory(event=event, hidden=True)
    RoomFactory()
    AvailabilityFactory(event=event, room=room)
    user = make_orga_user(event, can_change_event_settings=True)

    public_view = make_view(RoomViewSet, make_api_request(event=event))
    orga_view = make_view(RoomViewSet, make_api_request(event=event, user=user))
    public_rooms = list(public_view.get_queryset())
    orga_rooms = list(orga_view.get_queryset())

    assert public_rooms == [room]
    with django_assert_num_queries(1):
        assert len(public_rooms[0].availabilities.all()) == 1
    assert set(orga_rooms) == {room, hidden}
    with django_assert_num_queries(0):
        assert len(orga_rooms[orga_rooms.index(room)].availabilities.all()) == 1


def test_roomviewset_perform_destroy_raises_on_protected_room():
    slot = TalkSlotFactory()
    room = slot.room
    user = make_orga_user(room.event, can_change_event_settings=True)
    request = make_api_request(event=room.event, user=user)
    view = make_view(RoomViewSet, request)
    view.action = "destroy"

    with pytest.raises(exceptions.ValidationError, match="cannot delete"):
        view.perform_destroy(room)
