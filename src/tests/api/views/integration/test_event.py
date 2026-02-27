import pytest
from django_scopes import scopes_disabled

from pretalx.person.models.auth_token import ENDPOINTS, WRITE_PERMISSIONS
from tests.factories import EventFactory, TeamFactory, UserApiTokenFactory, UserFactory

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_event_list_shows_public_events(client):
    """Anonymous users can see public events in the event list."""
    with scopes_disabled():
        public_event = EventFactory(is_public=True)

    response = client.get("/api/events/", follow=True)

    assert response.status_code == 200
    data = response.json()
    slugs = [e["slug"] for e in data]
    assert public_event.slug in slugs


@pytest.mark.django_db
def test_event_list_hides_non_public_from_anonymous(client):
    """Anonymous users do not see non-public events."""
    with scopes_disabled():
        EventFactory(is_public=False)
        public_event = EventFactory(is_public=True)

    response = client.get("/api/events/", follow=True)

    assert response.status_code == 200
    data = response.json()
    slugs = [e["slug"] for e in data]
    assert len(slugs) == 1
    assert slugs[0] == public_event.slug


@pytest.mark.django_db
def test_event_list_shows_private_events_to_orga(client):
    """Authenticated organisers see both public and their private events."""
    with scopes_disabled():
        public_event = EventFactory(is_public=True)
        private_event = EventFactory(is_public=False)
        user = UserFactory()
        team = TeamFactory(organiser=private_event.organiser, all_events=True)
        team.members.add(user)
        token = UserApiTokenFactory(
            user=user, endpoints={ep: list(WRITE_PERMISSIONS) for ep in ENDPOINTS}
        )
        token.events.add(private_event)

    response = client.get(
        "/api/events/", follow=True, headers={"Authorization": f"Token {token.token}"}
    )

    assert response.status_code == 200
    data = response.json()
    slugs = {e["slug"] for e in data}
    assert public_event.slug in slugs
    assert private_event.slug in slugs


@pytest.mark.django_db
def test_event_list_serializer_fields(client):
    """Event list returns the expected subset of fields."""
    with scopes_disabled():
        EventFactory(is_public=True)

    response = client.get("/api/events/", follow=True)

    assert response.status_code == 200
    event_data = response.json()[0]
    expected_keys = {"name", "slug", "is_public", "date_from", "date_to", "timezone"}
    assert set(event_data.keys()) == expected_keys


@pytest.mark.django_db
def test_event_detail_accessible_for_public_event(client):
    """Anonymous users can view a public event's details."""
    with scopes_disabled():
        event = EventFactory(is_public=True)

    response = client.get(f"/api/events/{event.slug}/", follow=True)

    assert response.status_code == 200
    data = response.json()
    assert data["slug"] == event.slug
    assert "email" in data
    assert "locale" in data
    assert "locales" in data


@pytest.mark.django_db
def test_event_detail_returns_404_for_non_public_anonymous(client):
    """Anonymous users get 404 for a non-public event."""
    with scopes_disabled():
        event = EventFactory(is_public=False)

    response = client.get(f"/api/events/{event.slug}/", follow=True)

    assert response.status_code == 404


@pytest.mark.django_db
def test_event_detail_accessible_for_orga(client):
    """Authenticated organiser can view a non-public event's details."""
    with scopes_disabled():
        event = EventFactory(is_public=False)
        user = UserFactory()
        team = TeamFactory(organiser=event.organiser, all_events=True)
        team.members.add(user)
        token = UserApiTokenFactory(
            user=user, endpoints={ep: list(WRITE_PERMISSIONS) for ep in ENDPOINTS}
        )
        token.events.add(event)

    response = client.get(
        f"/api/events/{event.slug}/",
        follow=True,
        headers={"Authorization": f"Token {token.token}"},
    )

    assert response.status_code == 200
    assert response.json()["slug"] == event.slug


@pytest.mark.django_db
def test_event_detail_fields(client):
    """Event detail includes additional fields compared to the list view."""
    with scopes_disabled():
        event = EventFactory(is_public=True)

    response = client.get(f"/api/events/{event.slug}/", follow=True)

    assert response.status_code == 200
    data = response.json()
    detail_only_fields = {
        "email",
        "primary_color",
        "custom_domain",
        "locale",
        "locales",
        "content_locales",
    }
    assert detail_only_fields.issubset(data.keys())


@pytest.mark.django_db
def test_event_list_filter_by_is_public(client):
    """The is_public filter parameter controls which events are returned."""
    with scopes_disabled():
        EventFactory(is_public=True)
        EventFactory(is_public=True)
        EventFactory(is_public=False)

    response = client.get("/api/events/?is_public=true", follow=True)

    assert response.status_code == 200
    data = response.json()
    assert all(e["is_public"] for e in data)
    assert len(data) == 2


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_event_list_query_count(client, item_count, django_assert_num_queries):
    """Query count for anonymous event list is constant regardless of item count."""
    with scopes_disabled():
        for _ in range(item_count):
            EventFactory(is_public=True)

    with django_assert_num_queries(1):
        response = client.get("/api/events/", follow=True)

    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_event_list_orga_query_count(client, item_count, django_assert_num_queries):
    """Query count for authenticated orga event list is constant regardless of item count."""
    with scopes_disabled():
        user = UserFactory()
        for _ in range(item_count):
            event = EventFactory(is_public=False)
            team = TeamFactory(organiser=event.organiser, all_events=True)
            team.members.add(user)
        token = UserApiTokenFactory(
            user=user, endpoints={ep: list(WRITE_PERMISSIONS) for ep in ENDPOINTS}
        )

    with django_assert_num_queries(5):
        response = client.get(
            "/api/events/",
            follow=True,
            headers={"Authorization": f"Token {token.token}"},
        )

    assert response.status_code == 200
    assert len(response.json()) == item_count
