import pytest
from django_scopes import scopes_disabled

from pretalx.orga.views.typeahead import (
    serialize_admin_user,
    serialize_event,
    serialize_orga,
    serialize_speaker,
    serialize_submission,
    serialize_user,
)
from tests.factories import EventFactory, SpeakerFactory, SubmissionFactory, UserFactory

pytestmark = pytest.mark.unit


def test_serialize_user():
    user = UserFactory.build(name="Alice", email="alice@example.com")

    result = serialize_user(user)

    assert result == {"type": "user", "name": str(user), "url": "/orga/me"}


@pytest.mark.django_db
def test_serialize_orga(event):
    organiser = event.organiser

    result = serialize_orga(organiser)

    assert result == {
        "type": "organiser",
        "name": str(organiser.name),
        "url": organiser.orga_urls.base,
    }


@pytest.mark.django_db
def test_serialize_event(event):
    result = serialize_event(event)

    assert result == {
        "type": "event",
        "name": str(event.name),
        "url": event.orga_urls.base,
        "organiser": str(event.organiser.name),
        "date_range": event.get_date_range_display(),
    }


@pytest.mark.django_db
def test_serialize_submission():
    with scopes_disabled():
        submission = SubmissionFactory()

    result = serialize_submission(submission)

    assert result == {
        "type": "submission",
        "name": f"Session {submission.title}",
        "url": submission.orga_urls.base,
        "event": str(submission.event.name),
    }


@pytest.mark.django_db
def test_serialize_speaker():
    with scopes_disabled():
        event = EventFactory()
        speaker = SpeakerFactory(event=event)

    result = serialize_speaker(speaker)

    assert result == {
        "type": "speaker",
        "name": f"Speaker {speaker.get_display_name()}",
        "url": speaker.orga_urls.base,
        "event": str(event.name),
    }


@pytest.mark.django_db
def test_serialize_admin_user():
    user = UserFactory()

    result = serialize_admin_user(user)

    assert result == {
        "type": "user.admin",
        "name": f"User {user.get_display_name()}",
        "email": user.email,
        "url": user.orga_urls.admin,
    }
