import pytest
from django_scopes import scopes_disabled

from pretalx.api.serializers.event import EventListSerializer, EventSerializer
from pretalx.api.views.event import EventViewSet
from tests.factories import EventFactory, TeamFactory, UserFactory
from tests.utils import make_api_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_event_viewset_get_unversioned_serializer_class_list():
    """get_unversioned_serializer_class returns EventListSerializer for list action."""
    request = make_api_request()
    view = make_view(EventViewSet, request)
    view.action = "list"

    assert view.get_unversioned_serializer_class() is EventListSerializer


@pytest.mark.django_db
def test_event_viewset_get_unversioned_serializer_class_retrieve():
    """get_unversioned_serializer_class returns EventSerializer for retrieve action."""
    request = make_api_request()
    view = make_view(EventViewSet, request)
    view.action = "retrieve"

    assert view.get_unversioned_serializer_class() is EventSerializer


@pytest.mark.django_db
def test_event_viewset_get_queryset_anonymous_sees_only_public():
    """Anonymous users only see public events."""
    with scopes_disabled():
        public_event = EventFactory(is_public=True)
        EventFactory(is_public=False)
    request = make_api_request()
    view = make_view(EventViewSet, request)
    view.action = "list"

    qs = list(view.get_queryset())

    assert qs == [public_event]


@pytest.mark.django_db
def test_event_viewset_get_queryset_orga_sees_private_events():
    """Authenticated organisers see both public and their private events."""
    with scopes_disabled():
        public_event = EventFactory(is_public=True)
        private_event = EventFactory(is_public=False)
        user = UserFactory()
        team = TeamFactory(organiser=private_event.organiser, all_events=True)
        team.members.add(user)
    request = make_api_request(user=user)
    view = make_view(EventViewSet, request)
    view.action = "list"

    qs = list(view.get_queryset())

    assert set(qs) == {public_event, private_event}
