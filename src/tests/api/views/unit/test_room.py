import pytest
from django_scopes import scopes_disabled
from rest_framework import exceptions

from pretalx.api.serializers.room import RoomOrgaSerializer, RoomSerializer
from pretalx.api.views.room import RoomViewSet
from tests.factories import AvailabilityFactory, RoomFactory, TalkSlotFactory
from tests.utils import make_api_request, make_orga_user, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_roomviewset_get_queryset_returns_event_rooms():
    """get_queryset returns rooms belonging to the view's event."""
    with scopes_disabled():
        room = RoomFactory()
        other_room = RoomFactory()
    request = make_api_request(event=room.event)
    view = make_view(RoomViewSet, request)
    view.action = "list"

    with scopes_disabled():
        qs = list(view.get_queryset())

    assert qs == [room]
    assert other_room not in qs


@pytest.mark.django_db
def test_roomviewset_get_queryset_prefetches_availabilities_for_orga(
    django_assert_num_queries,
):
    """get_queryset prefetches availabilities when the user has update permission."""
    with scopes_disabled():
        room = RoomFactory()
        AvailabilityFactory(event=room.event, room=room)
        user = make_orga_user(room.event, can_change_event_settings=True)
    request = make_api_request(event=room.event, user=user)
    view = make_view(RoomViewSet, request)
    view.action = "list"

    with scopes_disabled():
        rooms = list(view.get_queryset())

    with django_assert_num_queries(0), scopes_disabled():
        availabilities = list(rooms[0].availabilities.all())
    assert len(availabilities) == 1


@pytest.mark.django_db
def test_roomviewset_get_queryset_no_prefetch_for_public(django_assert_num_queries):
    """get_queryset does NOT prefetch availabilities for users without update perm."""
    with scopes_disabled():
        room = RoomFactory()
        AvailabilityFactory(event=room.event, room=room)
    request = make_api_request(event=room.event)
    view = make_view(RoomViewSet, request)
    view.action = "list"

    with scopes_disabled():
        rooms = list(view.get_queryset())

    with django_assert_num_queries(1), scopes_disabled():
        list(rooms[0].availabilities.all())


@pytest.mark.django_db
def test_roomviewset_get_unversioned_serializer_class_returns_orga_for_write():
    """Non-safe methods return the orga serializer."""
    with scopes_disabled():
        room = RoomFactory()
    request = make_api_request(event=room.event, method="post")
    request._request.method = "POST"
    view = make_view(RoomViewSet, request)
    view.action = "create"

    cls = view.get_unversioned_serializer_class()

    assert cls is RoomOrgaSerializer


@pytest.mark.django_db
def test_roomviewset_get_unversioned_serializer_class_returns_orga_for_user_with_perm():
    """Safe methods return the orga serializer when user has update permission."""
    with scopes_disabled():
        room = RoomFactory()
        user = make_orga_user(room.event, can_change_event_settings=True)
    request = make_api_request(event=room.event, user=user)
    request._request.method = "GET"
    view = make_view(RoomViewSet, request)
    view.action = "list"

    cls = view.get_unversioned_serializer_class()

    assert cls is RoomOrgaSerializer


@pytest.mark.django_db
def test_roomviewset_get_unversioned_serializer_class_returns_public_for_anonymous():
    """Safe methods without update permission return the public serializer."""
    with scopes_disabled():
        room = RoomFactory()
    request = make_api_request(event=room.event)
    request._request.method = "GET"
    view = make_view(RoomViewSet, request)
    view.action = "list"

    cls = view.get_unversioned_serializer_class()

    assert cls is RoomSerializer


@pytest.mark.django_db
def test_roomviewset_perform_destroy_raises_on_protected_room():
    """Deleting a room with assigned talk slots raises a ValidationError."""
    with scopes_disabled():
        slot = TalkSlotFactory()
        room = slot.room
        user = make_orga_user(room.event, can_change_event_settings=True)
    request = make_api_request(event=room.event, user=user)
    view = make_view(RoomViewSet, request)
    view.action = "destroy"

    with (
        pytest.raises(exceptions.ValidationError, match="cannot delete"),
        scopes_disabled(),
    ):
        view.perform_destroy(room)
