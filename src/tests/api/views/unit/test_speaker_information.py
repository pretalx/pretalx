import pytest
from django_scopes import scopes_disabled

from pretalx.api.views.speaker_information import SpeakerInformationViewSet
from tests.factories import EventFactory, SpeakerInformationFactory, TrackFactory
from tests.utils import make_api_request, make_view

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_speakerinformationviewset_get_queryset_returns_event_information():
    """get_queryset returns speaker information belonging to the view's event."""
    with scopes_disabled():
        event = EventFactory()
        info = SpeakerInformationFactory(event=event)
        SpeakerInformationFactory()
    request = make_api_request(event=event)
    view = make_view(SpeakerInformationViewSet, request)
    view.action = "list"

    with scopes_disabled():
        qs = list(view.get_queryset())

    assert qs == [info]


@pytest.mark.django_db
def test_speakerinformationviewset_get_queryset_ordered_by_pk():
    """get_queryset orders results by primary key."""
    with scopes_disabled():
        event = EventFactory()
        info1 = SpeakerInformationFactory(event=event)
        info2 = SpeakerInformationFactory(event=event)
    request = make_api_request(event=event)
    view = make_view(SpeakerInformationViewSet, request)
    view.action = "list"

    with scopes_disabled():
        qs = list(view.get_queryset())

    assert qs == [info1, info2]


@pytest.mark.django_db
def test_speakerinformationviewset_get_queryset_prefetches_related(
    django_assert_num_queries,
):
    """get_queryset prefetches limit_tracks and limit_types."""
    with scopes_disabled():
        event = EventFactory()
        info = SpeakerInformationFactory(event=event)
        track = TrackFactory(event=event)
        info.limit_tracks.add(track)
    request = make_api_request(event=event)
    view = make_view(SpeakerInformationViewSet, request)
    view.action = "list"

    with scopes_disabled():
        items = list(view.get_queryset())

    with django_assert_num_queries(0):
        tracks = list(items[0].limit_tracks.all())
        list(items[0].limit_types.all())
    assert items[0].pk == info.pk
    assert tracks == [track]
