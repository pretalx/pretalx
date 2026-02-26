import datetime as dt

import pytest
from django_scopes import scopes_disabled

from tests.factories import EventFactory, TeamFactory, UserFactory

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_event_startpage_accessible_for_public_event(client, event):
    """Public event startpage returns 200."""
    event.is_public = True
    event.save()

    response = client.get(f"/{event.slug}/", follow=True)

    assert response.status_code == 200


@pytest.mark.django_db
def test_event_startpage_404_for_non_public_event(client, event):
    """Non-public event startpage returns 404 for anonymous users."""
    response = client.get(f"/{event.slug}/", follow=True)

    assert response.status_code == 404


@pytest.mark.django_db
def test_event_startpage_accessible_for_organiser_on_non_public_event(
    client, event, organiser_user
):
    """Organisers can access non-public event startpage."""
    client.force_login(organiser_user)

    response = client.get(f"/{event.slug}/", follow=True)

    assert response.status_code == 200


@pytest.mark.django_db
def test_event_startpage_404_for_nonexistent_event(client):
    """Typo'd event slug returns 404."""
    response = client.get("/nonexistent-event-slug/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_event_startpage_query_string_forwarded(client, event):
    """Query params (track, submission_type, access_code) appear in the rendered page."""
    event.is_public = True
    event.save()

    response = client.get(
        f"/{event.slug}/?track=main&submission_type=talk&access_code=abc123",
        follow=True,
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "track=main" in content
    assert "submission_type=talk" in content
    assert "access_code=abc123" in content


@pytest.mark.django_db
def test_event_cfp_page_accessible(client, event):
    """CfP page returns 200 for public event."""
    event.is_public = True
    event.save()

    response = client.get(f"/{event.slug}/cfp", follow=True)

    assert response.status_code == 200


@pytest.mark.django_db
def test_event_cfp_page_query_string_forwarded(client, event):
    """Query params on CfP page appear in the rendered page."""
    event.is_public = True
    event.save()

    response = client.get(
        f"/{event.slug}/cfp?track=main&submission_type=talk", follow=True
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "track=main" in content
    assert "submission_type=talk" in content


@pytest.mark.django_db
def test_general_view_lists_public_events(client):
    """Root page lists public events and hides non-public ones."""
    EventFactory(is_public=True, name="Public Conf")
    EventFactory(is_public=False, name="Private Conf")

    response = client.get("/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Public Conf" in content
    assert "Private Conf" not in content


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_general_view_query_count(client, item_count, django_assert_num_queries):
    """Query count stays constant regardless of how many public events exist."""
    events = [
        EventFactory(is_public=True, name=f"Event {i}") for i in range(item_count)
    ]

    with django_assert_num_queries(2):
        response = client.get("/")

    assert response.status_code == 200
    content = response.content.decode()
    assert all(str(e.name) in content for e in events)


@pytest.mark.django_db
def test_general_view_shows_non_public_events_to_organiser(client):
    """Root page shows non-public events to users with organiser permissions."""
    with scopes_disabled():
        private_event = EventFactory(is_public=False, name="Private Conf")
        user = UserFactory()
        team = TeamFactory(organiser=private_event.organiser, all_events=True)
        team.members.add(user)
    client.force_login(user)

    response = client.get("/")

    assert response.status_code == 200
    assert "Private Conf" in response.content.decode()


@pytest.mark.django_db
def test_general_view_categorizes_events_by_date(client):
    """Root page puts events in current, past, or future categories."""
    today = dt.date.today()
    current_event = EventFactory(
        is_public=True,
        name="Current Conf",
        date_from=today - dt.timedelta(days=1),
        date_to=today + dt.timedelta(days=1),
    )
    past_event = EventFactory(
        is_public=True,
        name="Past Conf",
        date_from=today - dt.timedelta(days=30),
        date_to=today - dt.timedelta(days=28),
    )
    future_event = EventFactory(
        is_public=True,
        name="Future Conf",
        date_from=today + dt.timedelta(days=30),
        date_to=today + dt.timedelta(days=32),
    )

    response = client.get("/")

    assert response.status_code == 200
    ctx = response.context
    current_names = [e.name for e in ctx["current_events"]]
    past_names = [e.name for e in ctx["past_events"]]
    future_names = [e.name for e in ctx["future_events"]]
    assert str(current_event.name) in current_names
    assert str(past_event.name) in past_names
    assert str(future_event.name) in future_names


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "expected_status"),
    (("/400", 400), ("/403", 403), ("/403/csrf", 403), ("/404", 404), ("/500", 500)),
)
def test_error_views_return_expected_status(client, path, expected_status):
    """Error debug views return their respective status codes."""
    response = client.get(path)

    assert response.status_code == expected_status
