# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django_scopes import scopes_disabled

from tests.factories import (
    EventFactory,
    OrganiserFactory,
    SpeakerFactory,
    SubmissionFactory,
    TeamFactory,
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

URL = "/orga/nav/typeahead/"


def _results(client, **params):
    response = client.get(URL, params)
    assert response.status_code == 200
    return [(r["type"], r["name"]) for r in response.json()["results"]]


def test_nav_typeahead_permission_filters(client, event):
    with scopes_disabled():
        SubmissionFactory(event=event, title="Secret submission data")

    response = client.get(URL)

    assert response.status_code == 302

    client.force_login(UserFactory())

    assert _results(client) == []

    client.force_login(make_orga_user(event, can_change_submissions=False))

    assert _results(client, query="Secret") == []


def test_nav_typeahead_event_and_organiser_results(client, event):
    with scopes_disabled():
        user = make_orga_user(event)
        user.name = "Nav Tester"
        user.save()
        event.organiser.name = f"{event.slug} organisation"
        event.organiser.save()
        event.custom_domain = "https://my.event.example.org"
        event.save()
        other_event = EventFactory(
            organiser=event.organiser,
            name="Other Event",
            custom_domain="https://other.example.com",
            date_from=event.date_from - dt.timedelta(days=30),
        )
    client.force_login(user)

    response = client.get(URL)

    assert response.status_code == 200
    data = response.json()
    assert data["has_more_events"] is False
    assert data["results"] == [
        {
            "type": "event",
            "name": str(event.name),
            "url": event.orga_urls.base,
            "organiser": f"{event.slug} organisation",
            "date_range": event.get_date_range_display(),
            "color": event.visible_primary_color,
        },
        {
            "type": "event",
            "name": "Other Event",
            "url": other_event.orga_urls.base,
            "organiser": f"{event.slug} organisation",
            "date_range": other_event.get_date_range_display(),
            "color": other_event.visible_primary_color,
        },
    ]
    assert _results(client, query="Other Event") == [("event", "Other Event")]
    assert _results(client, query=event.slug) == [
        ("event", str(event.name)),
        ("organiser", f"{event.slug} organisation"),
        ("event", "Other Event"),
    ]
    assert _results(client, query="my.event.example.org") == [
        ("event", str(event.name))
    ]
    assert _results(client, query="https://my.event.example.org") == [
        ("event", str(event.name))
    ]
    assert _results(client, query="organisation") == [
        ("organiser", f"{event.slug} organisation"),
        ("event", str(event.name)),
        ("event", "Other Event"),
    ]
    assert _results(client, query="Nav T") == [("user", "Nav Tester")]
    assert _results(client, query="zzznomatchzzz") == []
    assert _results(client, query="Nav T", organiser=event.organiser.pk) == [
        ("user", "Nav Tester"),
        ("organiser", f"{event.slug} organisation"),
    ]


def test_nav_typeahead_submission_speaker_and_admin_results(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        user.name = "Nav Tester"
        user.save()
        plain = SubmissionFactory(event=event, title="Plain talk")
        SubmissionFactory(event=event, title=f"About {plain.code} and more")
        k8s = SubmissionFactory(event=event, title="Kubernetes deep dive")
        k8s.speakers.add(SpeakerFactory(event=event, name="Guido van Rossum"))
        plain.speakers.add(
            SpeakerFactory(
                event=event,
                name="Contact Person",
                email="contact@example.com",
                user__name="Account Person",
                user__email="account@example.com",
            )
        )
        SpeakerFactory(event=event, name="Lonely Speaker")
        target_user = UserFactory(name="Findable Admin Target")
        admin = UserFactory(is_administrator=True)
    client.force_login(user)

    assert _results(client, query=plain.code) == [
        ("submission", "Session Plain talk"),
        ("submission", f"Session About {plain.code} and more"),
    ]
    assert _results(client, query="AB") == []
    assert _results(client, query="Kubernetes") == [
        ("submission", "Session Kubernetes deep dive")
    ]
    assert _results(client, query="Guido") == [("speaker", "Speaker Guido van Rossum")]
    assert _results(client, query="Contact@example.com") == [
        ("speaker", "Speaker Contact Person")
    ]
    assert _results(client, query="contact person") == [
        ("speaker", "Speaker Contact Person")
    ]
    assert _results(client, query="account@example.com") == []
    assert _results(client, query="account person") == []
    assert _results(client, query="Lonely") == []
    assert _results(client, query="Findable") == []

    client.force_login(admin)

    response = client.get(URL, {"query": "Findable"})
    assert response.json()["results"] == [
        {
            "type": "user.admin",
            "name": "User Findable Admin Target",
            "email": target_user.email,
            "url": target_user.orga_urls.admin,
        }
    ]


def test_nav_typeahead_pagination(client, event):
    with scopes_disabled():
        user = make_orga_user(event)
        for i in range(21):
            EventFactory(organiser=event.organiser, slug=f"evt{i:03d}")
    client.force_login(user)

    response = client.get(URL)

    data = response.json()
    assert len(data["results"]) == 5
    assert data["has_more_events"] is True

    page_one = client.get(URL, {"query": "evt", "page": "1"}).json()
    page_two = client.get(URL, {"query": "evt", "page": "2"}).json()

    assert page_one["pagination"] == {"more": True}
    assert page_two["pagination"] == {"more": False}
    names_one = {r["name"] for r in page_one["results"]}
    names_two = {r["name"] for r in page_two["results"]}
    assert len(names_one) == 20
    assert len(names_two) == 1
    assert names_one.isdisjoint(names_two)
    assert client.get(URL, {"query": "evt", "page": "notanumber"}).json() == page_one


def test_nav_typeahead_organiser_not_in_initial_slice_still_pinned(client):
    with scopes_disabled():
        user = UserFactory(name="Nav Tester")
        # Six organisers with a team for this user; the first five get events
        # so they rank higher and the sixth falls out of the initial slice.
        for i in range(6):
            orga = OrganiserFactory()
            TeamFactory(organiser=orga, all_events=True).members.add(user)
            if i < 5:
                EventFactory.create_batch(3, organiser=orga)
        target_orga = orga
    client.force_login(user)

    assert _results(client, query="Nav T", organiser=target_orga.pk) == [
        ("user", "Nav Tester"),
        ("organiser", str(target_orga.name)),
    ]
    assert _results(client, query="Nav T", organiser=target_orga.pk, page=2) == [
        ("user", "Nav Tester"),
        ("organiser", str(target_orga.name)),
    ]


@pytest.mark.parametrize("item_count", (1, 3))
def test_nav_typeahead_query_count_no_query(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        user = make_orga_user(event)
        EventFactory.create_batch(item_count - 1, organiser=event.organiser)
    client.force_login(user)

    with django_assert_num_queries(2):
        response = client.get(URL)

    assert response.status_code == 200
    results = response.json()["results"]
    event_results = [r for r in results if r["type"] == "event"]
    assert len(event_results) == item_count


@pytest.mark.parametrize("item_count", (1, 3))
def test_nav_typeahead_query_count_with_submissions(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        for i in range(item_count):
            sub = SubmissionFactory(event=event, title=f"Kubernetes talk {i}")
            speaker = SpeakerFactory(event=event, name=f"K8s Speaker {i}")
            sub.speakers.add(speaker)
    client.force_login(user)

    with django_assert_num_queries(10):
        response = client.get(URL, {"query": "Kubernetes"})

    assert response.status_code == 200
    results = response.json()["results"]
    submission_results = [r for r in results if r["type"] == "submission"]
    assert len(submission_results) == item_count
