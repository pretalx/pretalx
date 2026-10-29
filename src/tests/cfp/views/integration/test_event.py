# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.event.models.event import EventExtraLink
from tests.factories import (
    EventFactory,
    SubmitterAccessCodeFactory,
    TeamFactory,
    UserFactory,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("path", ("", "cfp"), ids=["startpage", "cfp_page"])
def test_event_pages_forward_query_string_to_submit_link(client, event, path):
    response = client.get(
        f"/{event.slug}/{path}?track=main&submission_type=talk&access_code=abc123",
        follow=True,
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "?track=main&amp;submission_type=talk&amp;access_code=abc123" in content


@pytest.mark.parametrize(
    ("with_code", "show_deadline"),
    ((True, True), (False, False)),
    ids=["with_code_deadline_shown", "without_code_deadline_hidden"],
)
def test_event_cfp_page_when_all_types_require_access_code(
    client, event, with_code, show_deadline
):
    with scopes_disabled():
        event.cfp.deadline = now() + dt.timedelta(days=5)
        event.cfp.settings["show_deadline"] = show_deadline
        event.cfp.save()
        event.submission_types.update(requires_access_code=True)
        access_code = SubmitterAccessCodeFactory(event=event)
    query = f"?access_code={access_code.code}" if with_code else ""

    response = client.get(f"/{event.slug}/cfp{query}", follow=True)

    assert response.status_code == 200
    content = response.content.decode()
    assert ("Submit a proposal" in content) is with_code
    assert ("Proposals are closed" in content) is not with_code
    assert "Submissions are only possible with an access code." in content
    assert ("Submissions close on" in content) is show_deadline


@pytest.mark.parametrize("with_code", (True, False), ids=["with_code", "without_code"])
def test_event_startpage_submit_link_when_all_types_require_access_code(
    client, event, with_code
):
    with scopes_disabled():
        event.submission_types.update(requires_access_code=True)
        access_code = SubmitterAccessCodeFactory(event=event)
    query = f"?access_code={access_code.code}" if with_code else ""

    response = client.get(f"/{event.slug}/{query}", follow=True)

    assert response.status_code == 200
    assert ("Submit a proposal" in response.content.decode()) is with_code


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
    assert list(ctx["current_events"]) == [current_event]
    assert list(ctx["past_events"]) == [past_event]
    assert list(ctx["future_events"]) == [future_event]


@pytest.mark.parametrize(
    ("path", "expected_status"),
    (("/400", 400), ("/403", 403), ("/403/csrf", 403), ("/404", 404), ("/500", 500)),
)
def test_error_views_return_expected_status(client, path, expected_status):
    response = client.get(path)

    assert response.status_code == expected_status


def test_404_under_public_event_shows_event_home_button_and_footer(client, event):
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
    # The heading text comes from a context-processor-provided phrase; if
    # RequestContext is not enabled, the heading is empty.
    assert "Page not found" in content
    assert "Event home" in content
    assert event.urls.base in content
    # We deliberately do not advertise the CfP, sessions, or speakers here.
    assert "Submit a proposal" not in content
    assert event.urls.submit not in content
    assert "Contact us" in content
    assert "Imprint" in content
    assert "https://example.com/imprint" in content
    assert "Code of Conduct" in content


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

    event.feature_flags["show_schedule"] = False
    event.save()

    response = client.get(f"/{event.slug}/no-such-page")

    assert response.status_code == 404
    content = response.content.decode()
    assert "Event home" in content
    assert event.urls.base in content
    assert event.urls.schedule not in content


def test_404_under_nonpublic_event_hides_event_button(client):
    event = EventFactory(is_public=False)
    response = client.get(f"/{event.slug}/", follow=True)

    assert response.redirect_chain == [
        (f"http://testserver/{event.slug}/login/?next=/{event.slug}/", 302)
    ]
    assert response.status_code == 404
    content = response.content.decode()
    assert event.urls.base not in content
    # Take-a-step-back is still offered.
    assert "Take a step back" in content


def test_404_without_event_renders_translated(client):
    response = client.get("/nonexistent-event-slug/")

    assert response.status_code == 404
    assert "Page not found" in response.content.decode()

    response = client.get("/nonexistent-event-slug/", headers={"accept-language": "de"})

    assert response.status_code == 404
    content = response.content.decode()
    assert "Seite nicht gefunden" in content
    assert "Page not found" not in content
