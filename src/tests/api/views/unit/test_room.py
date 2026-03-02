# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from rest_framework import exceptions

from pretalx.api.views.room import RoomViewSet
from tests.factories import AvailabilityFactory, RoomFactory, TalkSlotFactory
from tests.utils import make_api_request, make_orga_user, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_roomviewset_get_queryset_returns_event_rooms():
    room = RoomFactory()
    other_room = RoomFactory()
    request = make_api_request(event=room.event)
    view = make_view(RoomViewSet, request)
    view.action = "list"

    qs = list(view.get_queryset())

    assert qs == [room]
    assert other_room not in qs


def test_roomviewset_get_queryset_prefetches_availabilities_for_orga(
    django_assert_num_queries,
):
    room = RoomFactory()
    AvailabilityFactory(event=room.event, room=room)
    user = make_orga_user(room.event, can_change_event_settings=True)
    request = make_api_request(event=room.event, user=user)
    view = make_view(RoomViewSet, request)
    view.action = "list"

    rooms = list(view.get_queryset())

    with django_assert_num_queries(0):
        availabilities = list(rooms[0].availabilities.all())
    assert len(availabilities) == 1


def test_roomviewset_get_queryset_no_prefetch_for_public(django_assert_num_queries):
    room = RoomFactory()
    AvailabilityFactory(event=room.event, room=room)
    request = make_api_request(event=room.event)
    view = make_view(RoomViewSet, request)
    view.action = "list"

    rooms = list(view.get_queryset())

    with django_assert_num_queries(1):
        list(rooms[0].availabilities.all())


def test_roomviewset_perform_destroy_raises_on_protected_room():
    slot = TalkSlotFactory()
    room = slot.room
    user = make_orga_user(room.event, can_change_event_settings=True)
    request = make_api_request(event=room.event, user=user)
    view = make_view(RoomViewSet, request)
    view.action = "destroy"

    with pytest.raises(exceptions.ValidationError, match="cannot delete"):
        view.perform_destroy(room)
