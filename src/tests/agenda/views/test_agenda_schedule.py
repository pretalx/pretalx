# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
import textwrap
from urllib.parse import quote

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django_scopes import scope

from pretalx.person.models import SpeakerProfile


@pytest.mark.django_db
@pytest.mark.usefixtures("other_slot")
@pytest.mark.parametrize(("version", "queries"), (("js", 6), ("nojs", 8)))
def test_can_see_schedule(
    client, django_assert_num_queries, user, event, slot, version, queries
):
    with scope(event=event):
        del event.current_schedule
        assert user.has_perm("schedule.list_schedule", event)
        url = event.urls.schedule if version == "js" else event.urls.schedule_nojs

    with django_assert_num_queries(queries):
        response = client.get(url, follow=True, HTTP_ACCEPT="text/html")
    assert response.status_code == 200
    with scope(event=event):
        assert event.schedules.count() == 2
        test_string = "<pretalx-schedule" if version == "js" else slot.submission.title
        assert test_string in response.text


@pytest.mark.django_db
@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "lalala",
        }
    }
)
@pytest.mark.usefixtures("other_slot")
def test_can_see_changelog(
    client, django_assert_num_queries, user, event, slot, other_slot
):
    with scope(event=event):
        assert user.has_perm("schedule.list_schedule", event)
        wip_schedule = event.wip_schedule
        wip_slot = wip_schedule.talks.filter(submission=slot.submission).first()
        wip_slot.start += dt.timedelta(hours=1)
        wip_slot.save()
        event.release_schedule("v2")
        wip_slot = wip_schedule.talks.filter(submission=slot.submission).first()
        wip_slot.start += dt.timedelta(hours=1)
        wip_slot.save()
        event.release_schedule("v3")
        url = event.urls.schedule + "changelog/"

    with django_assert_num_queries(18):
        response = client.get(url, follow=True, HTTP_ACCEPT="text/html")

    assert response.status_code == 200
    assert slot.submission.title in response.content.decode()

    # Make sure that the next call uses fewer db queries, as the results are cached
    with django_assert_num_queries(15):
        response = client.get(url, follow=True, HTTP_ACCEPT="text/html")

    assert response.status_code == 200
    assert slot.submission.title in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("other_slot")
@pytest.mark.parametrize("version", ("js", "nojs"))
def test_orga_can_see_wip_schedule(orga_client, event, slot, version):
    with scope(event=event):
        url = event.urls.schedule + "v/wip/"
        if version != "js":
            url += "nojs"
    response = orga_client.get(url, follow=True, HTTP_ACCEPT="text/html")
    assert response.status_code == 200
    with scope(event=event):
        test_string = "<pretalx-schedule" if version == "js" else slot.submission.title
        assert test_string in response.text


@pytest.mark.django_db
@pytest.mark.usefixtures("other_slot")
@pytest.mark.parametrize(
    ("accept_header", "is_html"),
    (
        # curl/wget/httpie default
        ("*/*", False),
        # explicit text/plain
        ("text/plain", False),
        # Firefox/Safari
        ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", True),
        # Chrome/Edge
        (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            True,
        ),
        # Explicit HTML request
        ("text/html", True),
        # Broken/unknown accept header falls back to HTML
        ("foo/bar", True),
    ),
)
def test_schedule_content_negotiation(client, event, slot, accept_header, is_html):
    response = client.get(event.urls.schedule, follow=True, HTTP_ACCEPT=accept_header)
    assert response.status_code == 200
    if is_html:
        assert "text/html" in response.headers.get("Content-Type", "")
        assert "<pretalx-schedule" in response.text
    else:
        assert "text/plain" in response.headers.get("Content-Type", "")
        with scope(event=event):
            assert slot.submission.title[:10] in response.text


@pytest.mark.django_db
@pytest.mark.usefixtures("slot", "other_slot")
@pytest.mark.parametrize("featured", ("always", "never", "pre_schedule"))
def test_cannot_see_schedule_by_setting(client, user, event, featured):
    with scope(event=event):
        event.feature_flags["show_schedule"] = False
        event.save()
        assert not user.has_perm("schedule.list_schedule", event)
        event.feature_flags["show_featured"] = featured
        event.save()
    response = client.get(event.urls.schedule, HTTP_ACCEPT="text/html")
    if featured == "never":
        assert response.status_code == 404
    else:
        assert response.status_code == 302
        assert response.url == event.urls.featured


@pytest.mark.django_db
@pytest.mark.usefixtures("slot", "other_slot")
@pytest.mark.parametrize("featured", ("always", "never", "pre_schedule"))
def test_cannot_see_no_schedule(client, user, event, featured):
    with scope(event=event):
        event.current_schedule.talks.all().delete()
        event.current_schedule.delete()
        del event.current_schedule
        event.feature_flags["show_featured"] = featured
        event.save()
        assert not user.has_perm("schedule.list_schedule", event)
    response = client.get(event.urls.schedule, HTTP_ACCEPT="text/html")
    if featured == "never":
        assert response.status_code == 404
    else:
        assert response.status_code == 302
        assert response.url == event.urls.featured


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", [1, 2])
def test_speaker_list(
    client,
    django_assert_num_queries,
    event,
    speaker,
    other_speaker,
    slot,
    other_slot,
    item_count,
):
    if item_count != 2:
        with scope(event=event):
            SpeakerProfile.objects.filter(user=other_speaker, event=event).delete()

    with django_assert_num_queries(9):
        response = client.get(event.urls.speakers, follow=True)
    assert response.status_code == 200
    assert speaker.name in response.text
    if item_count == 2:
        assert other_speaker.name in response.text


@pytest.mark.django_db
@pytest.mark.usefixtures("other_slot")
def test_speaker_page(
    client, django_assert_num_queries, event, speaker_profile, slot, other_submission
):
    speaker = speaker_profile.user
    with scope(event=event):
        other_submission.speakers.add(speaker_profile)
        slot.submission.accept()
        slot.submission.save()
        event.wip_schedule.freeze("testversion 2")
        other_submission.slots.all().update(is_visible=True)
        slot.submission.slots.all().update(is_visible=True)
    url = reverse(
        "agenda:speaker", kwargs={"code": speaker_profile.code, "event": event.slug}
    )
    with django_assert_num_queries(12):
        response = client.get(url, follow=True)
    assert response.status_code == 200
    assert other_submission.title in response.content.decode()
    with scope(event=event):
        assert speaker.profiles.get(event=event).biography in response.text
        assert slot.submission.title in response.text


@pytest.mark.django_db
@pytest.mark.usefixtures("other_slot")
def test_speaker_page_other_submissions_only_if_visible(
    client,
    django_assert_num_queries,
    event,
    speaker,
    speaker_profile,
    slot,
    other_submission,
):
    with scope(event=event):
        other_submission.speakers.add(speaker_profile)
        slot.submission.accept()
        slot.submission.save()
        event.wip_schedule.freeze("testversion 2")
        other_submission.slots.all().update(is_visible=False)
        slot.submission.slots.filter(schedule=event.current_schedule).update(
            is_visible=True
        )

    url = reverse(
        "agenda:speaker",
        kwargs={"code": speaker_profile.code, "event": event.slug},
    )
    with django_assert_num_queries(12):
        response = client.get(url, follow=True)

    assert response.status_code == 200
    assert other_submission.title not in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("slot")
def test_speaker_social_media(
    client, django_assert_num_queries, event, speaker_profile
):
    url = reverse(
        "agenda:speaker-social",
        kwargs={"code": speaker_profile.code, "event": event.slug},
    )
    with django_assert_num_queries(8):
        response = client.get(url, follow=True)
    assert response.status_code == 404  # no images available


@pytest.mark.django_db
@pytest.mark.usefixtures("slot", "other_slot")
def test_speaker_redirect(client, event, speaker_profile):
    target_url = reverse(
        "agenda:speaker", kwargs={"code": speaker_profile.code, "event": event.slug}
    )
    url = event.urls.speakers + f"by-id/{speaker_profile.pk}/"
    response = client.get(url)
    assert response.status_code == 302
    assert response.headers["location"].endswith(target_url)


@pytest.mark.django_db
def test_speaker_redirect_unknown(client, event, submission):
    with scope(event=event):
        url = reverse(
            "agenda:speaker.redirect",
            kwargs={"pk": submission.speakers.first().pk, "event": event.slug},
        )
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.usefixtures("other_slot")
def test_schedule_page_text_table(client, django_assert_num_queries, event, slot):
    url = event.urls.schedule
    with django_assert_num_queries(8):
        response = client.get(url, follow=True)
    assert response.status_code == 200
    title_lines = textwrap.wrap(slot.submission.title, width=16)
    content = response.text
    for line in title_lines:
        assert line in content


@pytest.mark.parametrize(
    ("header", "target"),
    (
        ("application/json", "frab_json"),
        ("application/xml", "frab_xml"),
    ),
)
@pytest.mark.django_db
@pytest.mark.usefixtures("slot", "other_slot")
def test_schedule_page_redirects(
    client, django_assert_num_queries, event, header, target
):
    url = event.urls.schedule
    with django_assert_num_queries(6):
        response = client.get(url, HTTP_ACCEPT=header)
    assert response.status_code == 303
    assert response.headers["location"] == getattr(event.urls, target).full()
    assert response.text == ""


@pytest.mark.django_db
@pytest.mark.usefixtures("other_slot")
def test_schedule_page_text_list(client, django_assert_num_queries, event, slot):
    url = event.urls.schedule
    with django_assert_num_queries(8):
        response = client.get(url, {"format": "list"}, follow=True)
    assert response.status_code == 200
    assert slot.submission.title in response.text


@pytest.mark.django_db
@pytest.mark.usefixtures("other_slot")
def test_schedule_page_text_wrong_format(
    client, django_assert_num_queries, event, slot
):
    url = event.urls.schedule
    with django_assert_num_queries(8):
        response = client.get(url, {"format": "wrong"}, follow=True)
    assert response.status_code == 200
    assert slot.submission.title[:10] in response.text


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("version", "queries_main", "queries_versioned", "queries_redirect"),
    (("js", 6, 7, 13), ("nojs", 7, 10, 16)),
)
@pytest.mark.usefixtures("other_slot")
def test_versioned_schedule_page(
    client,
    django_assert_num_queries,
    event,
    slot,
    schedule,
    version,
    queries_main,
    queries_versioned,
    queries_redirect,
):
    with scope(event=event):
        event.release_schedule("new schedule")
        event.current_schedule.talks.update(is_visible=False)
        test_string = "<pretalx-schedule" if version == "js" else slot.submission.title

    url = event.urls.schedule if version == "js" else event.urls.schedule_nojs
    with django_assert_num_queries(queries_main):
        response = client.get(url, follow=True, HTTP_ACCEPT="text/html")
    if version == "js":
        # JS widget is displayed even on empty schedules
        assert test_string in response.text
    else:
        # But our talk has been made invisible
        assert test_string not in response.text

    url = schedule.urls.public if version == "js" else schedule.urls.nojs
    with django_assert_num_queries(queries_versioned):
        response = client.get(url, follow=True, HTTP_ACCEPT="text/html")
    assert response.status_code == 200
    assert test_string in response.text

    url = event.urls.schedule if version == "js" else event.urls.schedule_nojs
    url += f"?version={quote(schedule.version)}"
    with django_assert_num_queries(queries_redirect):
        redirected_response = client.get(url, follow=True, HTTP_ACCEPT="text/html")
    assert redirected_response._request.path == response._request.path


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("og_image", "logo", "header_image", "expected_status", "expected_content"),
    (
        (True, False, False, 200, b"og_content"),  # og_image set → returns it
        (
            False,
            True,
            False,
            200,
            b"logo_content",
        ),  # no og_image, logo set → returns logo
        (
            False,
            False,
            True,
            200,
            b"header_content",
        ),  # no og_image/logo, header_image → returns it
        (False, False, False, 404, None),  # nothing set → 404
        (
            True,
            True,
            True,
            200,
            b"og_content",
        ),  # all set → returns og_image (highest priority)
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
