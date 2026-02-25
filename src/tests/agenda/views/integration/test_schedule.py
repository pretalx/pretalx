import datetime as dt

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django_scopes import scope, scopes_disabled

from pretalx.submission.models import SubmissionStates
from tests.factories import SpeakerFactory, SubmissionFactory, TalkSlotFactory

pytestmark = pytest.mark.integration


@pytest.mark.django_db
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
    """The schedule view returns HTML for browser and unknown Accept headers."""
    response = client.get(
        public_event_with_schedule.urls.schedule, HTTP_ACCEPT=accept_header, follow=True
    )

    assert response.status_code == 200
    assert "text/html" in response["Content-Type"]
    assert "<pretalx-schedule" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "accept_kwargs",
    (
        pytest.param({"HTTP_ACCEPT": "*/*"}, id="curl_default"),
        pytest.param({}, id="no_accept_header"),
        pytest.param({"HTTP_ACCEPT": "text/plain"}, id="explicit_text_plain"),
    ),
)
def test_schedule_view_returns_text(client, public_event_with_schedule, accept_kwargs):
    """The schedule view returns plain text for non-HTML Accept headers."""
    response = client.get(public_event_with_schedule.urls.schedule, **accept_kwargs)

    assert response.status_code == 200
    assert "text/plain" in response["Content-Type"]
    assert str(public_event_with_schedule.name) in response.content.decode()


@pytest.mark.django_db
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
    """The schedule view returns 303 to the export URL for XML/JSON Accept headers."""
    event = public_event_with_schedule

    response = client.get(event.urls.schedule, HTTP_ACCEPT=accept_header)

    assert response.status_code == 303
    expected_url = getattr(event.urls, expected_url_attr).full()
    assert response.url == expected_url


@pytest.mark.django_db
def test_schedule_view_404_without_permission(client, event):
    """The schedule view returns 404 when the event is not public."""
    response = client.get(event.urls.schedule, HTTP_ACCEPT="text/html")

    assert response.status_code == 404


@pytest.mark.django_db
def test_schedule_view_404_without_published_schedule(client, event):
    """The schedule view returns 404 when no schedule has been released
    and featured is disabled."""
    event.is_public = True
    event.feature_flags["show_schedule"] = True
    event.feature_flags["show_featured"] = "never"
    event.save()

    response = client.get(event.urls.schedule, HTTP_ACCEPT="text/html")

    assert response.status_code == 404


@pytest.mark.django_db
def test_schedule_view_redirects_to_featured_when_not_released(client, event):
    """When schedule is not visible but featured is, redirect to featured page."""
    with scopes_disabled():
        SubmissionFactory(
            event=event, is_featured=True, state=SubmissionStates.CONFIRMED
        )
    event.is_public = True
    event.feature_flags["show_featured"] = "always"
    event.feature_flags["show_schedule"] = True
    event.save()

    response = client.get(event.urls.schedule, HTTP_ACCEPT="text/html")

    assert response.status_code == 302
    assert response.url == event.urls.featured


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("featured", "expected_status"),
    (
        pytest.param("always", 302, id="redirects_to_featured"),
        pytest.param("pre_schedule", 302, id="redirects_pre_schedule"),
        pytest.param("never", 404, id="404_without_featured"),
    ),
)
def test_schedule_view_disabled_schedule_with_featured_flags(
    client, event, featured, expected_status
):
    """When show_schedule is explicitly disabled, behavior depends on the featured flag."""
    with scopes_disabled():
        SubmissionFactory(
            event=event, is_featured=True, state=SubmissionStates.CONFIRMED
        )
    event.is_public = True
    event.feature_flags["show_schedule"] = False
    event.feature_flags["show_featured"] = featured
    event.save()

    response = client.get(event.urls.schedule, HTTP_ACCEPT="text/html")

    assert response.status_code == expected_status
    if expected_status == 302:
        assert response.url == event.urls.featured


@pytest.mark.django_db
def test_schedule_view_version_query_param_redirects(
    client, public_event_with_schedule
):
    """A ?version= query param causes a 301 redirect to the versioned URL."""
    response = client.get(
        public_event_with_schedule.urls.schedule + "?version=v1",
        HTTP_ACCEPT="text/html",
    )

    assert response.status_code == 301
    assert "v/v1" in response.url


@pytest.mark.django_db
def test_schedule_view_versioned_url(client, public_event_with_schedule):
    """Accessing a versioned schedule URL returns the correct schedule."""
    event = public_event_with_schedule
    with scopes_disabled():
        schedule = event.current_schedule

    response = client.get(
        f"/{event.slug}/schedule/v/{schedule.version}/", HTTP_ACCEPT="text/html"
    )

    assert response.status_code == 200
    assert "<pretalx-schedule" in response.content.decode()


@pytest.mark.django_db
def test_schedule_view_text_format_list(
    client, public_event_with_schedule, published_talk_slot
):
    """The text schedule supports ?format=list and includes talk titles."""
    response = client.get(
        public_event_with_schedule.urls.schedule + "?format=list", HTTP_ACCEPT="*/*"
    )

    assert response.status_code == 200
    assert "text/plain" in response["Content-Type"]
    assert published_talk_slot.submission.title in response.content.decode()


@pytest.mark.django_db
def test_schedule_view_text_format_invalid_falls_back_to_table(
    client, public_event_with_schedule
):
    """An invalid ?format= value falls back to the table format."""
    response = client.get(
        public_event_with_schedule.urls.schedule + "?format=invalid", HTTP_ACCEPT="*/*"
    )

    assert response.status_code == 200
    assert "text/plain" in response["Content-Type"]
    assert str(public_event_with_schedule.name) in response.content.decode()


@pytest.mark.django_db
def test_schedule_nojs_view_renders_with_talk_data(
    client, public_event_with_schedule, published_talk_slot
):
    """The nojs schedule view renders with schedule data including talk titles."""
    response = client.get(
        public_event_with_schedule.urls.schedule_nojs, HTTP_ACCEPT="text/html"
    )

    assert response.status_code == 200
    assert "agenda/schedule_nojs.html" in [t.name for t in response.templates]
    assert "data" in response.context
    assert "day_count" in response.context
    assert published_talk_slot.submission.title in response.content.decode()


@pytest.mark.django_db
def test_schedule_view_talk_url_renders(client, public_event_with_schedule):
    """The /talk/ URL renders the schedule view."""
    response = client.get(
        f"/{public_event_with_schedule.slug}/talk/", HTTP_ACCEPT="text/html"
    )

    assert response.status_code == 200
    assert "<pretalx-schedule" in response.content.decode()


@pytest.mark.django_db
def test_changelog_view_renders(client, public_event_with_schedule):
    """The changelog view renders with published schedule data."""
    event = public_event_with_schedule

    response = client.get(event.urls.changelog, HTTP_ACCEPT="text/html")

    assert response.status_code == 200
    assert "agenda/changelog.html" in [t.name for t in response.templates]
    content = response.content.decode()
    with scopes_disabled():
        schedule = event.current_schedule
    assert schedule.version in content


@pytest.mark.django_db
def test_changelog_view_404_without_permission(client, event):
    """The changelog returns 404 when schedule is not visible."""
    response = client.get(event.urls.changelog, HTTP_ACCEPT="text/html")

    assert response.status_code == 404


@pytest.mark.django_db
def test_changelog_view_empty_when_no_versions(client, organiser_user, event):
    """The changelog renders with an empty schedule list for an organiser
    when no schedule versions have been released."""
    client.force_login(organiser_user)

    response = client.get(event.urls.changelog, HTTP_ACCEPT="text/html")

    assert response.status_code == 200
    assert "agenda/changelog.html" in [t.name for t in response.templates]


@pytest.mark.django_db
def test_schedule_messages_returns_json(client, event):
    """The schedule messages endpoint returns JSON with all expected keys."""
    response = client.get(f"/{event.slug}/schedule/widget/messages.json")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    data = response.json()
    expected_keys = {
        "clear_filters",
        "favs_not_logged_in",
        "favs_not_saved",
        "filter",
        "filters",
        "jump_to_now",
        "languages",
        "no_matching_sessions",
        "not_recorded",
        "recording",
        "schedule_load_error",
        "schedule_empty",
        "show_results",
        "search",
        "see_also",
        "tags",
        "tracks",
    }
    assert set(data.keys()) == expected_keys
    assert all(isinstance(v, str) and v for v in data.values())


@pytest.mark.django_db
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
    """ExporterView returns exports for the standard format URLs."""
    response = client.get(f"/{public_event_with_schedule.slug}/schedule{url_suffix}")

    assert response.status_code == 200
    assert content_type in response["Content-Type"]


@pytest.mark.django_db
def test_exporter_view_404_for_unknown_exporter(client, public_event_with_schedule):
    """ExporterView returns 404 for an unknown exporter name."""
    response = client.get(
        f"/{public_event_with_schedule.slug}/schedule/export/nonexistent"
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_exporter_view_404_without_permission(client, event):
    """ExporterView returns 404 when user lacks schedule permission."""
    response = client.get(f"/{event.slug}/schedule.xml")

    assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_suffix", (pytest.param("", id="js"), pytest.param("nojs", id="nojs"))
)
def test_schedule_view_organizer_can_access_wip(client, user_with_event, url_suffix):
    """An organizer can access the WIP schedule via the versioned URL."""
    user, event = user_with_event
    client.force_login(user)

    response = client.get(
        f"/{event.slug}/schedule/v/wip/{url_suffix}", HTTP_ACCEPT="text/html"
    )

    assert response.status_code == 200


def _create_published_schedule(event, item_count):
    """Helper to create item_count talk slots and publish the schedule."""
    with scopes_disabled():
        for i in range(item_count):
            submission = SubmissionFactory(
                event=event, state=SubmissionStates.CONFIRMED
            )
            speaker = SpeakerFactory(event=event)
            submission.speakers.add(speaker)
            TalkSlotFactory(
                submission=submission,
                is_visible=True,
                start=event.datetime_from + dt.timedelta(hours=i),
                end=event.datetime_from + dt.timedelta(hours=i + 1),
            )
    with scope(event=event):
        event.wip_schedule.freeze("v1", notify_speakers=False)
    event.is_public = True
    event.feature_flags["show_schedule"] = True
    event.save()


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_schedule_view_text_query_count(
    client, event, item_count, django_assert_num_queries
):
    """Text schedule query count is constant regardless of talk count."""
    _create_published_schedule(event, item_count)

    with django_assert_num_queries(8):
        response = client.get(event.urls.schedule, HTTP_ACCEPT="*/*")

    assert response.status_code == 200
    assert "text/plain" in response["Content-Type"]


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_schedule_view_html_query_count(
    client, event, item_count, django_assert_num_queries
):
    """HTML schedule query count is constant regardless of talk count."""
    _create_published_schedule(event, item_count)

    with django_assert_num_queries(6):
        response = client.get(event.urls.schedule, HTTP_ACCEPT="text/html", follow=True)

    assert response.status_code == 200
    assert "text/html" in response["Content-Type"]


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_schedule_nojs_view_query_count(
    client, event, item_count, django_assert_num_queries
):
    """Nojs schedule query count is constant regardless of talk count."""
    _create_published_schedule(event, item_count)

    with django_assert_num_queries(8):
        response = client.get(event.urls.schedule_nojs, HTTP_ACCEPT="text/html")

    assert response.status_code == 200
    assert "agenda/schedule_nojs.html" in [t.name for t in response.templates]


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_changelog_view_query_count(
    client, event, item_count, django_assert_num_queries
):
    """Changelog query count is constant regardless of schedule version count."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        TalkSlotFactory(
            submission=submission,
            is_visible=True,
            start=event.datetime_from,
            end=event.datetime_from + dt.timedelta(hours=1),
        )
    event.is_public = True
    event.feature_flags["show_schedule"] = True
    event.save()
    with scope(event=event):
        for i in range(item_count):
            event.release_schedule(f"v{i + 1}")

    with django_assert_num_queries(8):
        response = client.get(event.urls.changelog, HTTP_ACCEPT="text/html")

    assert response.status_code == 200
    assert "agenda/changelog.html" in [t.name for t in response.templates]


@pytest.mark.django_db
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


@pytest.mark.django_db
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
    """EventSocialMediaCard returns the highest-priority image or 404."""
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
