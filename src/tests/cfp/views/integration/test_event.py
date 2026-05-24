# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django_scopes import scopes_disabled

from pretalx.event.models.event import EventExtraLink
from tests.factories import EventFactory, TeamFactory, UserFactory

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_event_startpage_404_for_non_public_event(client):
    event = EventFactory(is_public=False)
    response = client.get(f"/{event.slug}/", follow=True)

    assert response.status_code == 404


def test_event_startpage_404_for_nonexistent_event(client):
    response = client.get("/nonexistent-event-slug/")

    assert response.status_code == 404


def test_event_startpage_query_string_forwarded(client, event):
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
    events = EventFactory.create_batch(item_count, is_public=True)
    EventFactory(is_public=False, name="Private Conf")

    with django_assert_num_queries(1):
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


def test_404_under_public_event_shows_event_home_button(client, event):
    response = client.get(f"/{event.slug}/no-such-page")

    assert response.status_code == 404
    content = response.content.decode()
    # The heading text comes from a context-processor-provided phrase; if
    # RequestContext is not enabled, the heading is empty.
    assert "Page not found" in content
    assert "Event home" in content
    assert event.urls.base in content
    # We deliberately do not advertise the CfP, sessions, or speakers here.
    assert "Submit a proposal" not in content
    assert event.urls.submit not in content


def test_404_under_public_event_with_schedule_shows_schedule_button(
    client, public_event_with_schedule
):
    event = public_event_with_schedule
    response = client.get(f"/{event.slug}/no-such-page")

    assert response.status_code == 404
    content = response.content.decode()
    # Phrase labels come from `phrases.schedule.*`, only populated when the
    # `locale_context` context processor runs.
    assert "Schedule" in content
    assert event.urls.schedule in content
    # Only one event button; speakers/sessions are intentionally absent.
    assert event.urls.speakers not in content


def test_404_falls_back_to_event_home_when_show_schedule_disabled(
    client, public_event_with_schedule
):
    event = public_event_with_schedule
    event.feature_flags["show_schedule"] = False
    event.save()

    response = client.get(f"/{event.slug}/no-such-page")

    assert response.status_code == 404
    content = response.content.decode()
    # With show_schedule off, we link to the event home instead.
    assert "Event home" in content
    assert event.urls.base in content
    assert event.urls.schedule not in content


def test_404_under_nonpublic_event_hides_event_button(client):
    event = EventFactory(is_public=False)
    response = client.get(f"/{event.slug}/no-such-page")

    assert response.status_code == 404
    content = response.content.decode()
    assert event.urls.base not in content
    # Take-a-step-back is still offered.
    assert "Take a step back" in content


def test_404_without_event_renders(client):
    response = client.get("/totally-unknown-slug/no-such-page")

    assert response.status_code == 404
    # The page heading must still render even without an event or active
    # locale middleware.
    assert "Page not found" in response.content.decode()


def test_404_under_event_renders_footer_links(client, event):
    event.display_settings["imprint_url"] = "https://example.com/imprint"
    event.save()
    with scopes_disabled():
        EventExtraLink.objects.create(
            event=event,
            label="Code of Conduct",
            url="https://example.com/coc",
            role="footer",
        )

    response = client.get(f"/{event.slug}/no-such-page")

    assert response.status_code == 404
    content = response.content.decode()
    assert "Contact us" in content
    assert "Imprint" in content
    assert "https://example.com/imprint" in content
    assert "Code of Conduct" in content
