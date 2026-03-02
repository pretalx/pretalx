# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django_scopes import scope, scopes_disabled

from pretalx.submission.models import SubmissionStates
from tests.factories import EventFactory, SubmissionFactory
from tests.utils import make_published_schedule

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize(
    "accept_header",
    (
        pytest.param("text/html", id="explicit_html"),
        pytest.param(
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            id="firefox",
        ),
        pytest.param(
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
            "image/webp,image/apng,*/*;q=0.8",
            id="chrome",
        ),
        pytest.param("application/pdf", id="unknown_fallback"),
    ),
)
def test_schedule_view_returns_html(client, public_event_with_schedule, accept_header):
    response = client.get(
        public_event_with_schedule.urls.schedule, HTTP_ACCEPT=accept_header, follow=True
    )

    assert response.status_code == 200
    assert "text/html" in response["Content-Type"]
    assert "<pretalx-schedule" in response.content.decode()


@pytest.mark.parametrize(
    "accept_kwargs",
    (
        pytest.param({"HTTP_ACCEPT": "*/*"}, id="curl_default"),
        pytest.param({}, id="no_accept_header"),
        pytest.param({"HTTP_ACCEPT": "text/plain"}, id="explicit_text_plain"),
    ),
)
def test_schedule_view_returns_text(client, public_event_with_schedule, accept_kwargs):
    response = client.get(public_event_with_schedule.urls.schedule, **accept_kwargs)

    assert response.status_code == 200
    assert "text/plain" in response["Content-Type"]
    assert str(public_event_with_schedule.name) in response.content.decode()


@pytest.mark.parametrize(
    ("accept_header", "expected_url_attr"),
    (
        ("application/xml", "frab_xml"),
        ("text/xml", "frab_xml"),
        ("application/json", "frab_json"),
    ),
    ids=["application_xml", "text_xml", "application_json"],
)
def test_schedule_view_redirects_for_export_accept_types(
    client, public_event_with_schedule, accept_header, expected_url_attr
):
    event = public_event_with_schedule

    response = client.get(event.urls.schedule, HTTP_ACCEPT=accept_header)

    assert response.status_code == 303
    expected_url = getattr(event.urls, expected_url_attr).full()
    assert response.url == expected_url


def test_schedule_view_404_without_permission(client):
    event = EventFactory(is_public=False)

    response = client.get(event.urls.schedule, HTTP_ACCEPT="text/html")

    assert response.status_code == 404


def test_schedule_view_redirects_to_featured_when_not_released(client):
    event = EventFactory(feature_flags={"show_featured": "always"})
    with scopes_disabled():
        SubmissionFactory(
            event=event, is_featured=True, state=SubmissionStates.CONFIRMED
        )

    response = client.get(event.urls.schedule, HTTP_ACCEPT="text/html")

    assert response.status_code == 302
    assert response.url == event.urls.featured


def test_schedule_view_version_query_param_redirects(
    client, public_event_with_schedule
):
    response = client.get(
        public_event_with_schedule.urls.schedule + "?version=v1",
        HTTP_ACCEPT="text/html",
    )

    assert response.status_code == 301
    assert "v/v1" in response.url


def test_schedule_view_versioned_url(client, public_event_with_schedule):
    event = public_event_with_schedule
    with scopes_disabled():
        schedule = event.current_schedule

    response = client.get(
        f"/{event.slug}/schedule/v/{schedule.version}/", HTTP_ACCEPT="text/html"
    )

    assert response.status_code == 200
    assert "<pretalx-schedule" in response.content.decode()


def test_schedule_view_text_format_list(
    client, public_event_with_schedule, published_talk_slot
):
    response = client.get(
        public_event_with_schedule.urls.schedule + "?format=list", HTTP_ACCEPT="*/*"
    )

    assert response.status_code == 200
    assert "text/plain" in response["Content-Type"]
    assert published_talk_slot.submission.title in response.content.decode()


def test_schedule_view_text_format_invalid_falls_back_to_table(
    client, public_event_with_schedule
):
    response = client.get(
        public_event_with_schedule.urls.schedule + "?format=invalid", HTTP_ACCEPT="*/*"
    )

    assert response.status_code == 200
    assert "text/plain" in response["Content-Type"]
    assert str(public_event_with_schedule.name) in response.content.decode()


def test_schedule_view_talk_url_renders(client, public_event_with_schedule):
    response = client.get(
        f"/{public_event_with_schedule.slug}/talk/", HTTP_ACCEPT="text/html"
    )

    assert response.status_code == 200
    assert "<pretalx-schedule" in response.content.decode()


def test_changelog_view_404_without_permission(client):
    event = EventFactory(is_public=False)

    response = client.get(event.urls.changelog, HTTP_ACCEPT="text/html")

    assert response.status_code == 404


def test_changelog_view_empty_when_no_versions(client, organiser_user, event):
    client.force_login(organiser_user)

    response = client.get(event.urls.changelog, HTTP_ACCEPT="text/html")

    assert response.status_code == 200
    assert "agenda/changelog.html" in [t.name for t in response.templates]


def test_schedule_messages_returns_json(client, event):
    response = client.get(f"/{event.slug}/schedule/widget/messages.json")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    data = response.json()
    assert all(isinstance(v, str) and v for v in data.values())


@pytest.mark.parametrize(
    ("url_suffix", "content_type"),
    (
        (".xml", "text/xml"),
        (".json", "application/json"),
        (".ics", "text/calendar"),
        (".xcal", "text/xml"),
    ),
    ids=["xml", "json", "ics", "xcal"],
)
def test_exporter_view_returns_export(
    client, public_event_with_schedule, url_suffix, content_type
):
    response = client.get(f"/{public_event_with_schedule.slug}/schedule{url_suffix}")

    assert response.status_code == 200
    assert content_type in response["Content-Type"]


def test_exporter_view_404_for_unknown_exporter(client, public_event_with_schedule):
    response = client.get(
        f"/{public_event_with_schedule.slug}/schedule/export/nonexistent"
    )

    assert response.status_code == 404


def test_exporter_view_404_without_permission(client, event):
    response = client.get(f"/{event.slug}/schedule.xml")

    assert response.status_code == 404


@pytest.mark.parametrize(
    "url_suffix", (pytest.param("", id="js"), pytest.param("nojs", id="nojs"))
)
def test_schedule_view_organizer_can_access_wip(client, user_with_event, url_suffix):
    user, event = user_with_event
    client.force_login(user)

    response = client.get(
        f"/{event.slug}/schedule/v/wip/{url_suffix}", HTTP_ACCEPT="text/html"
    )

    assert response.status_code == 200


@pytest.mark.parametrize("item_count", (1, 3))
def test_schedule_view_text_query_count(
    client, event, item_count, django_assert_num_queries
):
    make_published_schedule(event, item_count)

    with django_assert_num_queries(8):
        response = client.get(event.urls.schedule, HTTP_ACCEPT="*/*")

    assert response.status_code == 200
    assert "text/plain" in response["Content-Type"]


@pytest.mark.parametrize("item_count", (1, 3))
def test_schedule_view_html_query_count(
    client, event, item_count, django_assert_num_queries
):
    make_published_schedule(event, item_count)

    with django_assert_num_queries(6):
        response = client.get(event.urls.schedule, HTTP_ACCEPT="text/html", follow=True)

    assert response.status_code == 200
    assert "text/html" in response["Content-Type"]


@pytest.mark.parametrize("item_count", (1, 3))
def test_schedule_nojs_view_renders_with_talk_data(
    client, event, item_count, django_assert_num_queries
):
    submissions = make_published_schedule(event, item_count)

    with django_assert_num_queries(8):
        response = client.get(event.urls.schedule_nojs, HTTP_ACCEPT="text/html")

    assert response.status_code == 200
    assert "agenda/schedule_nojs.html" in [t.name for t in response.templates]
    assert "data" in response.context
    assert "day_count" in response.context
    content = response.content.decode()
    assert all(sub.title in content for sub in submissions)


@pytest.mark.parametrize("item_count", (1, 3))
def test_changelog_view_renders(client, event, item_count, django_assert_num_queries):
    make_published_schedule(event, item_count)
    with scopes_disabled():
        for i in range(item_count - 1):
            event.release_schedule(f"v{i + 2}")

    with django_assert_num_queries(8):
        response = client.get(event.urls.changelog, HTTP_ACCEPT="text/html")

    assert response.status_code == 200
    assert "agenda/changelog.html" in [t.name for t in response.templates]
    content = response.content.decode()
    assert "v1" in content


def test_schedule_nojs_view_versioned_url_shows_old_content(
    client, public_event_with_schedule
):
    """A versioned nojs URL shows talks that were visible in that version,
    even when they are invisible on the current schedule."""
    event = public_event_with_schedule
    with scopes_disabled():
        old_version = event.current_schedule.version
        title = (
            event.current_schedule.talks.filter(is_visible=True)
            .first()
            .submission.title
        )
    with scope(event=event):
        event.release_schedule("v2")
        event.current_schedule.talks.update(is_visible=False)

    response = client.get(event.urls.schedule_nojs, HTTP_ACCEPT="text/html")
    assert title not in response.content.decode()

    response = client.get(
        f"/{event.slug}/schedule/v/{old_version}/nojs", HTTP_ACCEPT="text/html"
    )
    assert response.status_code == 200
    assert title in response.content.decode()


@pytest.mark.parametrize(
    ("og_image", "logo", "header_image", "expected_status", "expected_content"),
    (
        pytest.param(True, False, False, 200, b"og_content", id="og_image"),
        pytest.param(False, True, False, 200, b"logo_content", id="logo"),
        pytest.param(False, False, True, 200, b"header_content", id="header_image"),
        pytest.param(False, False, False, 404, None, id="nothing"),
        pytest.param(True, True, True, 200, b"og_content", id="all_set_prefers_og"),
    ),
)
def test_event_social_card_fallback(
    client, event, og_image, logo, header_image, expected_status, expected_content
):
    if og_image:
        event.og_image.save("og.png", SimpleUploadedFile("og.png", b"og_content"))
    if logo:
        event.logo.save("logo.png", SimpleUploadedFile("logo.png", b"logo_content"))
    if header_image:
        event.header_image.save(
            "header.png", SimpleUploadedFile("header.png", b"header_content")
        )
    event.save()

    response = client.get(event.urls.social_image, follow=True)

    assert response.status_code == expected_status
    if expected_status == 200:
        content = b"".join(response.streaming_content)
        assert content == expected_content
