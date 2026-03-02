# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from rest_framework import exceptions

from pretalx.api.serializers.room import RoomOrgaSerializer, RoomSerializer
from pretalx.api.views.room import RoomViewSet
from tests.factories import AvailabilityFactory, RoomFactory, TalkSlotFactory
from tests.utils import make_api_request, make_orga_user, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_roomviewset_get_queryset_returns_event_rooms():
    """get_queryset returns rooms belonging to the view's event."""
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
    """get_queryset prefetches availabilities when the user has update permission."""
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
    """get_queryset does NOT prefetch availabilities for users without update perm."""
    room = RoomFactory()
    AvailabilityFactory(event=room.event, room=room)
    request = make_api_request(event=room.event)
    view = make_view(RoomViewSet, request)
    view.action = "list"

    rooms = list(view.get_queryset())

    with django_assert_num_queries(1):
        list(rooms[0].availabilities.all())


def test_roomviewset_get_unversioned_serializer_class_returns_orga_for_write():
    """Non-safe methods return the orga serializer."""
    room = RoomFactory()
    request = make_api_request(event=room.event, method="post")
    request._request.method = "POST"
    view = make_view(RoomViewSet, request)
    view.action = "create"

    cls = view.get_unversioned_serializer_class()

    assert cls is RoomOrgaSerializer


def test_roomviewset_get_unversioned_serializer_class_returns_orga_for_user_with_perm():
    """Safe methods return the orga serializer when user has update permission."""
    room = RoomFactory()
    user = make_orga_user(room.event, can_change_event_settings=True)
    request = make_api_request(event=room.event, user=user)
    request._request.method = "GET"
    view = make_view(RoomViewSet, request)
    view.action = "list"

    cls = view.get_unversioned_serializer_class()

    assert cls is RoomOrgaSerializer


def test_roomviewset_get_unversioned_serializer_class_returns_public_for_anonymous():
    """Safe methods without update permission return the public serializer."""
    room = RoomFactory()
    request = make_api_request(event=room.event)
    request._request.method = "GET"
    view = make_view(RoomViewSet, request)
    view.action = "list"

    cls = view.get_unversioned_serializer_class()

    assert cls is RoomSerializer


def test_roomviewset_perform_destroy_raises_on_protected_room():
    """Deleting a room with assigned talk slots raises a ValidationError."""
    slot = TalkSlotFactory()
    room = slot.room
    user = make_orga_user(room.event, can_change_event_settings=True)
    request = make_api_request(event=room.event, user=user)
    view = make_view(RoomViewSet, request)
    view.action = "destroy"

    with pytest.raises(exceptions.ValidationError, match="cannot delete"):
        view.perform_destroy(room)
