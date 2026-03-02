# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scopes_disabled

from pretalx.person.models.auth_token import ENDPOINTS, WRITE_PERMISSIONS
from tests.factories import EventFactory, TeamFactory, UserApiTokenFactory, UserFactory

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("item_count", (1, 3))
def test_event_list_shows_public_events(client, item_count, django_assert_num_queries):
    """Anonymous users see public events, non-public events are hidden,
    and query count is constant regardless of event count."""
    with scopes_disabled():
        public_events = EventFactory.create_batch(item_count, is_public=True)
        hidden_event = EventFactory(is_public=False)

    with django_assert_num_queries(1):
        response = client.get("/api/events/", follow=True)

    assert response.status_code == 200
    data = response.json()
    slugs = [e["slug"] for e in data]
    assert all(e.slug in slugs for e in public_events)
    assert hidden_event.slug not in slugs


@pytest.mark.parametrize("item_count", (1, 3))
def test_event_list_shows_events_to_orga(client, item_count, django_assert_num_queries):
    """Authenticated organisers see their private events, and query count
    is constant regardless of event count."""
    with scopes_disabled():
        user = UserFactory()
        events = []
        for _ in range(item_count):
            event = EventFactory(is_public=False)
            team = TeamFactory(organiser=event.organiser, all_events=True)
            team.members.add(user)
            events.append(event)
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
    data = response.json()
    slugs = {e["slug"] for e in data}
    assert all(e.slug in slugs for e in events)
    assert len(data) == item_count


def test_event_detail_accessible_for_public_event(client):
    with scopes_disabled():
        event = EventFactory(is_public=True)

    response = client.get(f"/api/events/{event.slug}/", follow=True)

    assert response.status_code == 200
    data = response.json()
    assert data["slug"] == event.slug
    assert "email" in data
    assert "locale" in data
    assert "locales" in data


def test_event_detail_returns_404_for_non_public_anonymous(client):
    with scopes_disabled():
        event = EventFactory(is_public=False)

    response = client.get(f"/api/events/{event.slug}/", follow=True)

    assert response.status_code == 404


def test_event_detail_fields(client):
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


def test_event_list_filter_by_is_public(client):
    with scopes_disabled():
        EventFactory.create_batch(2, is_public=True)
        EventFactory(is_public=False)

    response = client.get("/api/events/?is_public=true", follow=True)

    assert response.status_code == 200
    data = response.json()
    assert all(e["is_public"] for e in data)
    assert len(data) == 2
