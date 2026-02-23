# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import json
import os
from pathlib import Path

import pytest
import urllib3
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import CommandError
from django.test import override_settings
from django.urls import reverse
from django_scopes import scope, scopes_disabled
from jsonschema import validate
from lxml import etree

from pretalx.agenda.tasks import export_schedule_html
from pretalx.common.models.file import CachedFile
from pretalx.event.models import Event
from pretalx.person.models import ProfilePicture
from pretalx.submission.models import Resource


@pytest.mark.skipif(
    "CI" not in os.environ or not os.environ["CI"],
    reason="No need to bother with this outside of CI.",
)
def test_schedule_xsd_is_up_to_date():
    """If this test fails:

    http -d https://raw.githubusercontent.com/voc/schedule/master/validator/xsd/schedule.xml.xsd >! src/tests/fixtures/schedule.xsd
    """
    http = urllib3.PoolManager()
    response = http.request(
        "GET",
        "https://raw.githubusercontent.com/voc/schedule/master/validator/xsd/schedule.xml.xsd",
    )
    if response.status == 429:  # pragma: no cover
        # don’t fail tests on rate limits
        return
    assert response.status == 200
    path = Path(__file__).parent / "../fixtures/schedule.xsd"
    schema_content = path.read_text()
    assert response.data.decode() == schema_content


@pytest.mark.skipif(
    "CI" not in os.environ or not os.environ["CI"],
    reason="No need to bother with this outside of CI.",
)
def test_schedule_json_schema_is_up_to_date():
    """If this test fails:

    http -d https://raw.githubusercontent.com/voc/schedule/master/validator/json/schema.json >! src/tests/fixtures/schedule.json
    """
    http = urllib3.PoolManager()
    response = http.request(
        "GET",
        "https://raw.githubusercontent.com/voc/schedule/master/validator/json/schema.json",
    )
    if response.status == 429:  # pragma: no cover
        # don’t fail tests on rate limits
        return
    assert response.status == 200
    path = Path(__file__).parent / "../fixtures/schedule.json"
    schema_content = path.read_text()
    assert response.data.decode() == schema_content


@pytest.mark.django_db
@pytest.mark.usefixtures("break_slot")
def test_schedule_frab_xml_export(
    slot, client, django_assert_num_queries, schedule_schema_xml
):
    with django_assert_num_queries(13):
        response = client.get(
            reverse(
                "agenda:export.schedule.xml",
                kwargs={"event": slot.submission.event.slug},
            ),
            follow=True,
        )
    assert response.status_code == 200, str(response.text)
    assert "ETag" in response

    content = response.text
    assert slot.submission.title in content
    assert slot.submission.urls.public.full() in content

    parser = etree.XMLParser(schema=schedule_schema_xml)
    etree.fromstring(
        response.content, parser
    )  # Will raise if the schedule does not match the schema
    with django_assert_num_queries(11):
        response = client.get(
            reverse(
                "agenda:export.schedule.xml",
                kwargs={"event": slot.submission.event.slug},
            ),
            HTTP_IF_NONE_MATCH=response["ETag"].strip('"'),
            follow=True,
        )
    assert response.status_code == 304


@pytest.mark.django_db
def test_schedule_frab_xml_export_control_char(slot, client, django_assert_num_queries):
    slot.submission.description = "control char: \a"
    slot.submission.save()

    with django_assert_num_queries(12):
        response = client.get(
            reverse(
                "agenda:export.schedule.xml",
                kwargs={"event": slot.submission.event.slug},
            ),
            follow=True,
        )

    parser = etree.XMLParser()
    etree.fromstring(response.content, parser)


@pytest.mark.django_db
@pytest.mark.usefixtures("break_slot")
def test_schedule_frab_json_export(
    slot, client, django_assert_num_queries, orga_user, schedule_schema_json
):
    with django_assert_num_queries(14):
        regular_response = client.get(
            reverse(
                "agenda:export.schedule.json",
                kwargs={"event": slot.submission.event.slug},
            ),
            follow=True,
        )
    client.force_login(orga_user)
    with django_assert_num_queries(15):
        orga_response = client.get(
            reverse(
                "agenda:export.schedule.json",
                kwargs={"event": slot.submission.event.slug},
            ),
            follow=True,
        )
    assert regular_response.status_code == 200
    assert orga_response.status_code == 200

    regular_content = regular_response.text
    orga_content = orga_response.text

    assert slot.submission.title in regular_content
    assert slot.submission.title in orga_content

    regular_content = json.loads(regular_content)
    orga_content = json.loads(orga_content)
    assert regular_content["schedule"]
    assert orga_content["schedule"]

    assert regular_content == orga_content

    validate(instance=regular_content, schema=schedule_schema_json)


@pytest.mark.django_db
@pytest.mark.usefixtures("break_slot")
def test_schedule_frab_xcal_export(slot, client, django_assert_num_queries):
    with django_assert_num_queries(10):
        response = client.get(
            reverse(
                "agenda:export.schedule.xcal",
                kwargs={"event": slot.submission.event.slug},
            ),
            follow=True,
        )
    assert response.status_code == 200

    content = response.text
    assert slot.submission.title in content


@pytest.mark.django_db
def test_schedule_ical_export(slot, orga_client, django_assert_num_queries):
    with django_assert_num_queries(13):
        response = orga_client.get(
            reverse(
                "agenda:export.schedule.ics",
                kwargs={"event": slot.submission.event.slug},
            ),
            follow=True,
        )
        assert response.status_code == 200

    content = response.text
    assert slot.submission.title in content


@pytest.mark.django_db
def test_schedule_single_ical_export(slot, client, django_assert_num_queries):
    with django_assert_num_queries(13):
        response = client.get(slot.submission.urls.ical, follow=True)
    assert response.status_code == 200

    content = response.text
    assert slot.submission.title in content


@pytest.mark.django_db
@pytest.mark.parametrize(
    "exporter",
    ("schedule.xml", "schedule.json", "schedule.xcal", "schedule.ics", "feed"),
)
def test_schedule_export_nonpublic(exporter, slot, client, django_assert_num_queries):
    slot.submission.event.is_public = False
    slot.submission.event.save()
    exporter = "feed" if exporter == "feed" else f"export.{exporter}"

    with django_assert_num_queries(5):
        response = client.get(
            reverse(f"agenda:{exporter}", kwargs={"event": slot.submission.event.slug}),
            follow=True,
        )
    assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("exporter", "queries"),
    (("schedule.xml", 13), ("schedule.json", 14), ("schedule.xcal", 10), ("feed", 10)),
)
def test_schedule_export_public(
    exporter, queries, slot, client, django_assert_num_queries
):
    exporter = "feed" if exporter == "feed" else f"export.{exporter}"

    with django_assert_num_queries(queries):
        response = client.get(
            reverse(f"agenda:{exporter}", kwargs={"event": slot.submission.event.slug}),
            follow=True,
        )
    assert response.status_code == 200


@pytest.mark.django_db
def test_schedule_speaker_ical_export(
    slot, other_slot, client, django_assert_num_queries
):
    with scope(event=slot.submission.event):
        profile = slot.submission.speakers.all()[0]
    with django_assert_num_queries(14):
        response = client.get(profile.urls.talks_ical, follow=True)
    assert response.status_code == 200

    content = response.text
    assert slot.submission.title in content
    assert other_slot.submission.title not in content


@pytest.mark.django_db
def test_feed_view(slot, client, django_assert_num_queries, schedule):
    with django_assert_num_queries(10):
        response = client.get(slot.submission.event.urls.feed)
    assert response.status_code == 200
    assert schedule.version in response.text


@pytest.mark.django_db
def test_feed_view_with_control_characters(slot, client, schedule):
    schedule.version = "Version\x0b1"
    schedule.save()
    response = client.get(slot.submission.event.urls.feed)
    assert response.status_code == 200
    assert "Version1" in response.text
    assert "\x0b" not in response.text


@pytest.mark.django_db
def test_html_export_event_required():
    from django.core.management import (  # noqa: PLC0415
        call_command,
    )  # Import here to avoid overriding mocks

    with pytest.raises(CommandError) as excinfo:
        call_command("export_schedule_html")

    assert "the following arguments are required: event" in str(excinfo.value)


@pytest.mark.django_db
def test_html_export_event_unknown(event):
    from django.core.management import (  # noqa: PLC0415
        call_command,
    )  # Import here to avoid overriding mocks

    with pytest.raises(CommandError) as excinfo:
        call_command("export_schedule_html", "foobar222")
    assert 'Could not find event with slug "foobar222"' in str(excinfo.value)
    export_schedule_html(event_id=22222)
    export_schedule_html(event_id=event.pk)


@pytest.mark.django_db
@pytest.mark.usefixtures("slot")
def test_html_export_language(event):
    # Import here to avoid overriding mocks
    from django.core.management import call_command  # noqa: PLC0415

    event.locale = "de"
    event.locale_array = "de,en"
    event.save()
    call_command("rebuild")
    call_command("export_schedule_html", event.slug)

    export_path = settings.HTMLEXPORT_ROOT / "test" / "test/schedule/index.html"
    schedule_html = export_path.read_text()
    assert "Kontakt" in schedule_html
    assert "locale/set" not in schedule_html  # bug #494


@pytest.mark.django_db
@pytest.mark.usefixtures("slot")
def test_schedule_export_schedule_html_task(mocker, event):
    mocker.patch("django.core.management.call_command")
    from django.core.management import (  # noqa: PLC0415
        call_command,
    )  # Import here to avoid overriding mocks

    cached_file = CachedFile.objects.create(
        expires="2099-01-01T00:00:00Z",
        filename="test.zip",
        content_type="application/zip",
    )
    export_schedule_html.apply_async(
        kwargs={"event_id": event.id, "cached_file_id": str(cached_file.id)}
    )

    call_command.assert_called_with("export_schedule_html", event.slug, "--zip")


@pytest.mark.django_db
def test_schedule_orga_trigger_export_redirects_to_download(orga_client, event):
    response = orga_client.post(event.orga_urls.schedule_export_trigger, follow=False)
    assert response.status_code == 302
    assert response.url == event.orga_urls.schedule_export_download


@pytest.mark.django_db
@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "trigger-test",
        }
    }
)
def test_schedule_orga_trigger_export_clears_cached_file(orga_client, event):
    event.__dict__.pop("cache", None)
    cached_file = CachedFile.objects.create(
        expires="2099-01-01T00:00:00Z",
        filename="test.zip",
        content_type="application/zip",
    )
    event.cache.set("schedule_export_cached_file", str(cached_file.id), None)

    response = orga_client.post(event.orga_urls.schedule_export_trigger, follow=False)
    assert response.status_code == 302
    assert not CachedFile.objects.filter(pk=cached_file.pk).exists()


@pytest.mark.parametrize("use_zip", (True, False))
@pytest.mark.django_db
def test_html_export_full(
    event, other_event, slot, confirmed_resource, canceled_talk, orga_client, use_zip
):
    from django.core.management import (  # noqa: PLC0415
        call_command,
    )  # Import here to avoid overriding mocks

    event.primary_color = "#111111"
    event.is_public = False
    event.save()
    other_event.primary_color = "#222222"
    other_event.save()

    nonascii_filename = "lüstíg.jpg"
    f = SimpleUploadedFile(nonascii_filename, b"file_content")
    with scope(event=event):
        profile = slot.submission.speakers.first()
        picture = ProfilePicture.objects.create(user=profile.user)
        picture.avatar.save(nonascii_filename, f)
        picture.save()
        profile.user.profile_picture = picture
        profile.user.save()
        profile.profile_picture = picture
        profile.save()
        avatar_filename = picture.avatar.name.split("/")[-1]
        resource = Resource.objects.create(submission=slot.submission)
        resource.resource.save(nonascii_filename, f)
        resource.save()
        resource_filename = resource.resource.name.split("/")[-1]
        slot.submission.image.save(nonascii_filename, f)
        slot.submission.save()
        image_filename = slot.submission.image.name.split("/")[-1]

    call_command("rebuild")
    event = Event.objects.get(slug=event.slug)
    args = ["export_schedule_html", event.slug]
    if use_zip:
        args.append("--zip")
    call_command(*args)

    if use_zip:
        full_path = settings.HTMLEXPORT_ROOT / "test.zip"
        assert full_path.exists()
        return

    with scope(event=event):
        speaker_paths = [
            f"test/speaker/{profile.code}/index.html"
            for profile in slot.submission.speakers.all()
        ]

    paths = [
        "static/common/img/icons/favicon.ico",
        f"media/test/submissions/{slot.submission.code}/resources/{resource_filename}",
        f"media/test/submissions/{slot.submission.code}/{image_filename}",
        f"media/avatars/{avatar_filename}",
        "test/schedule/index.html",
        "test/schedule/export/schedule.json",
        "test/schedule/export/schedule.xcal",
        "test/schedule/export/schedule.xml",
        *speaker_paths,
        f"test/talk/{slot.submission.code}/index.html",
        f"test/talk/{slot.submission.code}.ics",
        confirmed_resource.resource.url.lstrip("/"),
    ]

    for path in paths:
        full_path = settings.HTMLEXPORT_ROOT / "test" / path
        assert full_path.exists()

    for path in (settings.HTMLEXPORT_ROOT / "test/media/").glob("*"):
        path_str = str(path)
        assert event.slug in path_str
        assert other_event.slug not in path_str

    # views and templates are the same for export and online viewing, so a naive test is enough here
    html_path = (
        settings.HTMLEXPORT_ROOT
        / "test"
        / f"test/talk/{slot.submission.code}/index.html"
    )
    talk_html = html_path.read_text()
    assert talk_html.count(slot.submission.title) >= 2

    with scope(event=event):
        profile = slot.submission.speakers.all()[0]
    html_path = settings.HTMLEXPORT_ROOT / "test" / "test/schedule/index.html"
    schedule_html = html_path.read_text()
    assert "Contact us" in schedule_html  # locale
    assert canceled_talk.submission.title not in schedule_html

    schedule_json = json.load(
        (settings.HTMLEXPORT_ROOT / "test/test/schedule/export/schedule.json").open()
    )
    assert schedule_json["schedule"]["conference"]["title"] == event.name

    xcal_path = settings.HTMLEXPORT_ROOT / "test/test/schedule/export/schedule.xcal"
    schedule_xcal = xcal_path.read_text()
    assert event.slug in schedule_xcal
    assert profile.get_display_name() in schedule_xcal

    xml_path = settings.HTMLEXPORT_ROOT / "test/test/schedule/export/schedule.xml"
    schedule_xml = xml_path.read_text()
    with scope(event=slot.submission.event):
        assert slot.submission.title in schedule_xml
        assert canceled_talk.frab_slug not in schedule_xml
        assert str(canceled_talk.uuid) not in schedule_xml

    ics_path = settings.HTMLEXPORT_ROOT / f"test/test/talk/{slot.submission.code}.ics"
    talk_ics = ics_path.read_text()
    assert slot.submission.title in talk_ics
    assert event.is_public is False

    # Downloads always generate a fresh export via Celery (runs inline in eager mode),
    # so query count includes the full HTML export generation.
    response = orga_client.get(event.orga_urls.schedule_export_download, follow=True)
    assert response.status_code == 200


@pytest.mark.django_db
def test_speaker_csv_export(slot, orga_client, django_assert_num_queries):
    with django_assert_num_queries(14):
        response = orga_client.get(
            reverse(
                "agenda:export",
                kwargs={"event": slot.submission.event.slug, "name": "speakers.csv"},
            ),
            follow=True,
        )
    assert response.status_code == 200, str(response.text)
    with scopes_disabled():
        assert slot.submission.speakers.first().get_display_name() in response.text


@pytest.mark.django_db
def test_empty_speaker_csv_export(orga_client, django_assert_num_queries, event):
    with django_assert_num_queries(10):
        response = orga_client.get(
            reverse(
                "agenda:export", kwargs={"event": event.slug, "name": "speakers.csv"}
            ),
            follow=True,
        )
    assert response.status_code == 200, str(response.text)
    assert len(response.text) < 100


@pytest.mark.django_db
@pytest.mark.usefixtures(
    "answer", "answered_choice_question", "impersonal_answer", "personal_answer"
)
def test_submission_question_csv_export(slot, orga_client):
    response = orga_client.get(
        reverse(
            "agenda:export",
            kwargs={
                "event": slot.submission.event.slug,
                "name": "submission-questions.csv",
            },
        ),
        follow=True,
    )
    assert response.status_code == 200, str(response.text)
    assert slot.submission.title in response.text


@pytest.mark.django_db
@pytest.mark.usefixtures(
    "answer", "answered_choice_question", "impersonal_answer", "personal_answer"
)
def test_speaker_question_csv_export(slot, orga_client):
    response = orga_client.get(
        reverse(
            "agenda:export",
            kwargs={
                "event": slot.submission.event.slug,
                "name": "speaker-questions.csv",
            },
        ),
        follow=True,
    )
    assert response.status_code == 200, str(response.text)
    with scopes_disabled():
        assert slot.submission.speakers.first().get_display_name() in response.text


@pytest.mark.django_db
def test_wrong_export(slot, orga_client):
    response = orga_client.get(
        reverse(
            "agenda:export",
            kwargs={"event": slot.submission.event.slug, "name": "wrong"},
        ),
        follow=True,
    )
    assert response.status_code == 404


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
def test_schedule_download_starts_async_task(mocker, orga_client, schedule):
    mock_result = mocker.MagicMock()
    mock_result.id = "test-task-id"
    mocker.patch(
        "pretalx.agenda.tasks.export_schedule_html.apply_async",
        return_value=mock_result,
    )

    response = orga_client.get(
        schedule.event.orga_urls.schedule_export_download, follow=False
    )

    assert response.status_code == 302
    assert "async_id=test-task-id" in response.url


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
def test_schedule_download_htmx_polling_pending(mocker, orga_client, schedule):
    mock_result = mocker.MagicMock()
    mock_result.ready.return_value = False
    mocker.patch("celery.result.AsyncResult", return_value=mock_result)

    response = orga_client.get(
        f"{schedule.event.orga_urls.schedule_export_download}?async_id=test-id",
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"Generating" in response.content


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
def test_schedule_download_htmx_polling_success(mocker, orga_client, schedule):
    cached_file = CachedFile.objects.create(
        expires="2099-01-01T00:00:00Z",
        filename="test.zip",
        content_type="application/zip",
    )
    cached_file.file.save("test.zip", ContentFile(b"zipdata"))

    mock_result = mocker.MagicMock()
    mock_result.ready.return_value = True
    mock_result.successful.return_value = True
    mock_result.result = str(cached_file.id)
    mocker.patch("celery.result.AsyncResult", return_value=mock_result)

    response = orga_client.get(
        f"{schedule.event.orga_urls.schedule_export_download}?async_id=test-id",
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"Download ready" in response.content
    assert b"Download" in response.content


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
def test_schedule_download_htmx_polling_failure(mocker, orga_client, schedule):
    mock_result = mocker.MagicMock()
    mock_result.ready.return_value = True
    mock_result.successful.return_value = False
    mocker.patch("celery.result.AsyncResult", return_value=mock_result)

    response = orga_client.get(
        f"{schedule.event.orga_urls.schedule_export_download}?async_id=test-id",
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"Export failed" in response.content


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
def test_schedule_download_non_htmx_waiting(mocker, orga_client, schedule):
    mock_result = mocker.MagicMock()
    mock_result.ready.return_value = False
    mocker.patch("celery.result.AsyncResult", return_value=mock_result)

    response = orga_client.get(
        f"{schedule.event.orga_urls.schedule_export_download}?async_id=test-id"
    )

    assert response.status_code == 200
    assert b"Generating" in response.content


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
def test_schedule_download_non_htmx_failure(mocker, orga_client, schedule):
    mock_result = mocker.MagicMock()
    mock_result.ready.return_value = True
    mock_result.successful.return_value = False
    mocker.patch("celery.result.AsyncResult", return_value=mock_result)

    response = orga_client.get(
        f"{schedule.event.orga_urls.schedule_export_download}?async_id=test-id",
        follow=True,
    )

    assert response.status_code == 200
    assert b"Export failed" in response.content
