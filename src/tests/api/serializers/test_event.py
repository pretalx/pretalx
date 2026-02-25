import pytest
from django.contrib.auth.models import AnonymousUser

from pretalx.api.serializers.event import EventListSerializer, EventSerializer
from tests.factories import EventFactory, UserFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_event_list_serializer_data():
    event = EventFactory()
    data = EventListSerializer(event).data
    assert data == {
        "name": {"en": event.name},
        "slug": event.slug,
        "is_public": event.is_public,
        "date_from": event.date_from.isoformat(),
        "date_to": event.date_to.isoformat(),
        "timezone": event.timezone,
    }


@pytest.mark.django_db
def test_event_serializer_data():
    event = EventFactory()
    data = EventSerializer(event).data
    assert data == {
        "name": {"en": event.name},
        "slug": event.slug,
        "is_public": event.is_public,
        "date_from": event.date_from.isoformat(),
        "date_to": event.date_to.isoformat(),
        "timezone": event.timezone,
        "email": event.email,
        "primary_color": event.primary_color,
        "custom_domain": event.custom_domain,
        "logo": None,
        "header_image": None,
        "og_image": None,
        "locale": event.locale,
        "locales": event.locales,
        "content_locales": event.content_locales,
    }


@pytest.mark.django_db
def test_event_list_serializer_clears_timezone_choices_no_request():
    """Without a request in context, timezone choices are cleared for smaller API docs."""
    event = EventFactory()
    serializer = EventListSerializer(event)
    assert not serializer.fields["timezone"].choices


@pytest.mark.django_db
def test_event_list_serializer_clears_timezone_choices_unauthenticated(rf):
    """Unauthenticated users get empty timezone choices."""
    event = EventFactory()
    request = rf.get("/")
    request.user = AnonymousUser()
    serializer = EventListSerializer(event, context={"request": request})
    assert not serializer.fields["timezone"].choices


@pytest.mark.django_db
def test_event_list_serializer_keeps_timezone_choices_authenticated(rf):
    """Authenticated users keep the full timezone choice list."""
    event = EventFactory()
    user = UserFactory()
    request = rf.get("/")
    request.user = user
    serializer = EventListSerializer(event, context={"request": request})
    assert serializer.fields["timezone"].choices
