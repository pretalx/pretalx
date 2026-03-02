# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django_scopes import scopes_disabled

from tests.factories import EventFactory, TeamFactory, UserFactory

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_event_startpage_404_for_non_public_event(client):
    """Non-public event startpage returns 404 for anonymous users."""
    event = EventFactory(is_public=False)
    response = client.get(f"/{event.slug}/", follow=True)

    assert response.status_code == 404


def test_event_startpage_404_for_nonexistent_event(client):
    response = client.get("/nonexistent-event-slug/")

    assert response.status_code == 404


def test_event_startpage_query_string_forwarded(client, event):
    """Query params (track, submission_type, access_code) appear in the rendered page."""
    response = client.get(
        f"/{event.slug}/?track=main&submission_type=talk&access_code=abc123",
        follow=True,
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "track=main" in content
    assert "submission_type=talk" in content
    assert "access_code=abc123" in content


def test_event_cfp_page_query_string_forwarded(client, event):
    response = client.get(
        f"/{event.slug}/cfp?track=main&submission_type=talk", follow=True
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "track=main" in content
    assert "submission_type=talk" in content


@pytest.mark.parametrize("item_count", (1, 3))
def test_general_view_lists_public_events(
    client, item_count, django_assert_num_queries
):
    """Root page lists public events, hides non-public ones, with constant query count."""
    events = EventFactory.create_batch(item_count, is_public=True)
    EventFactory(is_public=False, name="Private Conf")

    with django_assert_num_queries(2):
        response = client.get("/")

    assert response.status_code == 200
    content = response.content.decode()
    assert all(str(e.name) in content for e in events)
    assert "Private Conf" not in content


def test_general_view_shows_non_public_events_to_organiser(client):
    with scopes_disabled():
        private_event = EventFactory(is_public=False, name="Private Conf")
        user = UserFactory()
        team = TeamFactory(organiser=private_event.organiser, all_events=True)
        team.members.add(user)
    client.force_login(user)

    response = client.get("/")

    assert response.status_code == 200
    assert "Private Conf" in response.content.decode()


def test_general_view_categorizes_events_by_date(client):
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


@pytest.mark.parametrize(
    ("path", "expected_status"),
    (("/400", 400), ("/403", 403), ("/403/csrf", 403), ("/404", 404), ("/500", 500)),
)
def test_error_views_return_expected_status(client, path, expected_status):
    response = client.get(path)

    assert response.status_code == expected_status
