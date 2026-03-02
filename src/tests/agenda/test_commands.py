# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import HttpResponse, StreamingHttpResponse
from django.test import override_settings

from pretalx.agenda.management.commands.export_schedule_html import (
    delete_directory,
    dump_content,
    event_exporter_urls,
    event_speaker_urls,
    event_talk_urls,
    event_urls,
    export_event,
    fake_admin,
    find_assets,
    find_urls,
    get_content,
    get_export_path,
    get_export_zip_path,
    get_mediastatic_content,
    get_path,
    schedule_version_urls,
)
from pretalx.common.exporter import BaseExporter
from pretalx.common.signals import register_data_exporters
from pretalx.event.models import Event
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    EventFactory,
    ResourceFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
)

pytestmark = pytest.mark.unit


class _PublicExporter(BaseExporter):
    public = True
    filename_identifier = "test-public"
    extension = "xml"
    verbose_name = "Test Public"
    icon = "fa-test"


class _DynamicPublicExporter(BaseExporter):
    """Has a dynamic is_public method, so event_exporter_urls skips it
    to prevent data leakage from dynamic exporters."""

    public = True
    filename_identifier = "test-dynamic"
    extension = "xml"
    verbose_name = "Test Dynamic"
    icon = "fa-test"

    def is_public(self, request, **kwargs):
        return True  # pragma: no cover -- not called intentionally


class _NonPublicExporter(BaseExporter):
    public = False
    filename_identifier = "test-nonpublic"
    extension = "xml"
    verbose_name = "Test Non-Public"
    icon = "fa-test"


@pytest.mark.parametrize(
    ("html", "expected"),
    (
        (
            b'<html><body><script src="/static/app.js"></script></body></html>',
            "/static/app.js",
        ),
        (b'<html><body><img src="/media/photo.png"></body></html>', "/media/photo.png"),
        (
            b'<html><head><link rel="stylesheet" href="/static/style.css"></head></html>',
            "/static/style.css",
        ),
        (
            b'<html><head><link rel="icon" href="/static/favicon.ico"></head></html>',
            "/static/favicon.ico",
        ),
        (
            b'<html><body><a data-lightbox="/media/big.jpg">click</a></body></html>',
            "/media/big.jpg",
        ),
    ),
    ids=["script_src", "img_src", "stylesheet_href", "icon_href", "lightbox_data"],
)
def test_find_assets_extracts_single_asset(html, expected):
    result = list(find_assets(html))

    assert result == [expected]


@pytest.mark.parametrize(
    ("html", "expected"),
    (
        (
            b'<html><body><a data-lightbox="" href="/media/img.jpg">click</a></body></html>',
            ["/media/img.jpg"],
        ),
        (
            b'<html><body><div data-lightbox="" src="/media/img.jpg"></div></body></html>',
            ["/media/img.jpg"],
        ),
        (b'<html><body><span data-lightbox="">text</span></body></html>', []),
    ),
    ids=["fallback_to_href", "fallback_to_src", "no_url_skipped"],
)
def test_find_assets_lightbox_fallback(html, expected):
    result = list(find_assets(html))

    assert result == expected


def test_find_assets_extracts_multiple_assets():
    html = (
        b'<html><head><link rel="stylesheet" href="/static/a.css">'
        b'<link rel="icon" href="/static/favicon.ico"></head>'
        b'<body><script src="/static/b.js"></script>'
        b'<img src="/media/c.png"></body></html>'
    )

    result = list(find_assets(html))

    assert set(result) == {
        "/static/a.css",
        "/static/favicon.ico",
        "/static/b.js",
        "/media/c.png",
    }


def test_find_assets_ignores_script_without_src():
    html = b"<html><body><script>console.log('hi')</script></body></html>"

    result = list(find_assets(html))

    assert result == []


@pytest.mark.parametrize(
    ("css", "expected"),
    (
        (b'body { background: url("/static/bg.png"); }', {"/static/bg.png"}),
        (
            b'a { background: url("/static/a.png"); } b { background: url(/static/b.png); }',
            {"/static/a.png", "/static/b.png"},
        ),
        (b"body { color: red; }", set()),
    ),
    ids=["single_url", "quoted_and_unquoted", "no_urls"],
)
def test_find_urls_extracts_css_url_references(css, expected):
    assert set(find_urls(css)) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    (("https://example.com/foo/bar?q=1", "/foo/bar"), ("/foo/bar", "/foo/bar")),
    ids=["full_url", "path_only"],
)
def test_get_path_extracts_path_component(url, expected):
    assert get_path(url) == expected


def test_get_content_returns_body_for_non_streaming():
    response = HttpResponse(b"hello")

    assert get_content(response) == b"hello"


def test_get_content_joins_streaming_content():
    response = StreamingHttpResponse(iter([b"hel", b"lo"]))

    assert get_content(response) == b"hello"


@pytest.mark.parametrize(
    ("url_path", "expected_file", "content"),
    (
        ("/test/page.html", "test/page.html", b"file content"),
        ("/section/", "section/index.html", b"index page"),
        ("/a/b/c/file.txt", "a/b/c/file.txt", b"deep"),
        ("/media/l%C3%BCstig.jpg", "media/lüstig.jpg", b"decoded"),
    ),
    ids=[
        "basic_file",
        "trailing_slash_appends_index",
        "creates_parent_dirs",
        "urlencoded_path",
    ],
)
def test_dump_content_writes_to_expected_path(
    tmp_path, url_path, expected_file, content
):
    result = dump_content(tmp_path, url_path, lambda _path: content)

    assert (tmp_path / expected_file).read_bytes() == content
    assert result == content


def test_dump_content_raises_on_path_traversal(tmp_path):
    with pytest.raises(CommandError, match="Path traversal"):
        dump_content(tmp_path, "/../../../etc/passwd", None)


def test_get_mediastatic_content_reads_static_file(tmp_path):
    static_file = tmp_path / "static" / "test.css"
    static_file.parent.mkdir(parents=True)
    static_file.write_bytes(b"css content")

    with override_settings(
        STATIC_URL="/static/",
        STATIC_ROOT=tmp_path / "static",
        MEDIA_ROOT=tmp_path / "media",
    ):
        result = get_mediastatic_content("/static/test.css")

    assert result == b"css content"


def test_get_mediastatic_content_reads_media_file(tmp_path):
    media_file = tmp_path / "media" / "photo.png"
    media_file.parent.mkdir(parents=True)
    media_file.write_bytes(b"png data")

    with override_settings(
        MEDIA_URL="/media/",
        MEDIA_ROOT=tmp_path / "media",
        STATIC_ROOT=tmp_path / "static",
    ):
        result = get_mediastatic_content("/media/photo.png")

    assert result == b"png data"


def test_get_mediastatic_content_raises_for_unknown_prefix():
    with pytest.raises(FileNotFoundError):
        get_mediastatic_content("/unknown/path.txt")


def test_get_mediastatic_content_raises_for_directory_traversal(tmp_path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (tmp_path / "secret.txt").write_text("secret")

    with (
        override_settings(
            STATIC_URL="/static/", STATIC_ROOT=static_dir, MEDIA_ROOT=tmp_path / "media"
        ),
        pytest.raises(FileNotFoundError),
    ):
        get_mediastatic_content("/static/../secret.txt")


def test_get_mediastatic_content_decodes_urlencoded_path(tmp_path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "lüstig.css").write_bytes(b"encoded css")

    with override_settings(
        STATIC_URL="/static/", STATIC_ROOT=static_dir, MEDIA_ROOT=tmp_path / "media"
    ):
        result = get_mediastatic_content("/static/l%C3%BCstig.css")

    assert result == b"encoded css"


def test_delete_directory_removes_existing(tmp_path):
    target = tmp_path / "to_delete"
    target.mkdir()
    (target / "file.txt").write_text("data")

    delete_directory(target)

    assert not target.exists()


def test_delete_directory_ignores_nonexistent(tmp_path):
    delete_directory(tmp_path / "does_not_exist")


@pytest.mark.django_db
def test_get_export_path_returns_event_slug_under_root():
    event = EventFactory(slug="myconf")

    result = get_export_path(event)

    assert result == settings.HTMLEXPORT_ROOT / "myconf"


@pytest.mark.django_db
def test_get_export_zip_path_returns_zip_suffix():
    event = EventFactory(slug="myconf")

    result = get_export_zip_path(event)

    assert result == settings.HTMLEXPORT_ROOT / "myconf.zip"


@pytest.mark.django_db
def test_event_talk_urls_yields_public_ical_and_resource_urls():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    resource = ResourceFactory(submission=submission, is_public=True)
    resource.resource.save("res.pdf", SimpleUploadedFile("res.pdf", b"pdf data"))
    TalkSlotFactory(submission=submission, is_visible=True)
    event.wip_schedule.freeze("v1", notify_speakers=False)
    event = Event.objects.get(pk=event.pk)

    result = list(event_talk_urls(event))

    assert result == [
        submission.urls.public,
        submission.urls.ical,
        resource.resource.url,
    ]


@pytest.mark.django_db
def test_event_talk_urls_skips_resource_without_file():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    ResourceFactory(submission=submission, is_public=True)
    TalkSlotFactory(submission=submission, is_visible=True)
    event.wip_schedule.freeze("v1", notify_speakers=False)
    event = Event.objects.get(pk=event.pk)

    result = list(event_talk_urls(event))

    assert result == [submission.urls.public, submission.urls.ical]


@pytest.mark.django_db
def test_event_speaker_urls_yields_public_and_ical():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    TalkSlotFactory(submission=submission, is_visible=True)
    event.wip_schedule.freeze("v1", notify_speakers=False)
    event = Event.objects.get(pk=event.pk)

    result = list(event_speaker_urls(event))

    assert result == [speaker.urls.public, speaker.urls.talks_ical]


@pytest.mark.django_db
def test_event_urls_includes_all_url_categories():
    event = EventFactory()

    result = list(event_urls(event))

    assert event.urls.base in result
    assert event.urls.schedule in result
    assert event.urls.schedule + "widget/messages.json" in result
    assert event.urls.schedule_nojs in result
    assert event.urls.schedule_widget_data in result
    assert event.urls.featured in result
    assert event.urls.talks in result
    assert event.urls.speakers in result
    assert event.urls.changelog in result
    assert event.urls.feed in result


@pytest.mark.django_db
def test_schedule_version_urls_yields_urls_for_versioned_schedules():
    """Only versioned schedules are included; the WIP schedule (version=None) is not."""
    event = EventFactory()
    TalkSlotFactory(submission__event=event, is_visible=True)
    event.wip_schedule.freeze("v1", notify_speakers=False)
    schedule = event.schedules.get(version="v1")

    result = list(schedule_version_urls(event))

    assert result == [
        schedule.urls.public,
        schedule.urls.widget_data,
        schedule.urls.nojs,
    ]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("exporter_cls", "should_include"),
    (
        (_PublicExporter, True),
        (_DynamicPublicExporter, False),
        (_NonPublicExporter, False),
    ),
    ids=["public_yields_url", "dynamic_is_public_skipped", "non_public_skipped"],
)
def test_event_exporter_urls_filters_by_public_attribute(
    register_signal_handler, exporter_cls, should_include
):
    """Yields URLs only for exporters with public=True and no dynamic is_public
    property, to prevent data leakage from dynamic exporters."""
    event = EventFactory()
    register_signal_handler(
        register_data_exporters, lambda signal, sender, **kwargs: exporter_cls
    )

    result = list(event_exporter_urls(event))

    exporter_url = str(exporter_cls(event).urls.base)
    if should_include:
        assert exporter_url in [str(u) for u in result]
    else:
        assert exporter_url not in [str(u) for u in result]


@pytest.mark.django_db
def test_fake_admin_reverts_event_changes():
    """fake_admin sets is_public=True and show_schedule during the context,
    but the rolledback_transaction reverts changes after."""
    event = EventFactory(is_public=False)

    with fake_admin(event):
        assert event.is_public is True

    event.refresh_from_db()
    assert event.is_public is False


@pytest.mark.django_db
def test_fake_admin_getter_returns_response_content():
    event = EventFactory()
    TalkSlotFactory(submission__event=event, is_visible=True)
    event.wip_schedule.freeze("v1", notify_speakers=False)
    event = Event.objects.get(pk=event.pk)

    with fake_admin(event) as get:
        content = get(f"/{event.slug}/schedule/")

    assert str(event.name).encode() in content


@pytest.mark.slow
@pytest.mark.django_db
@pytest.mark.filterwarnings(
    "ignore:It looks like you're using an HTML parser to parse an XML document"
)
def test_export_event_creates_output_and_resolves_media_urls(tmp_path):
    """export_event creates schedule HTML, includes uploaded resources, and
    resolves CSS url() references (e.g. font files referenced from base.css)."""
    call_command("collectstatic", "--no-input", verbosity=0)
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    resource = ResourceFactory(submission=submission, is_public=True)
    resource.resource.save("test.pdf", SimpleUploadedFile("test.pdf", b"pdf data"))
    slot = TalkSlotFactory(submission=submission, is_visible=True)
    slot.schedule.freeze("v1", notify_speakers=False)

    export_event(event, tmp_path)

    assert (tmp_path / event.slug / "schedule" / "index.html").exists()
    resource_path = tmp_path / resource.resource.url.lstrip("/")
    assert resource_path.exists()
    font_files = list((tmp_path / "static" / "fonts").glob("*"))
    assert font_files


@pytest.mark.django_db
def test_export_schedule_html_command_creates_directory_and_zip():
    event = EventFactory()

    call_command("export_schedule_html", event.slug)
    export_dir = settings.HTMLEXPORT_ROOT / event.slug
    assert export_dir.exists()
    assert (export_dir / event.slug / "schedule" / "index.html").exists()
    delete_directory(export_dir)

    call_command("export_schedule_html", event.slug, "--zip")
    zip_path = settings.HTMLEXPORT_ROOT / f"{event.slug}.zip"
    assert zip_path.exists()
    assert not export_dir.exists()
    zip_path.unlink()


@pytest.mark.django_db
def test_export_schedule_html_command_wraps_failure_in_command_error():
    event = EventFactory()

    def failing_export(_event, _destination):
        raise RuntimeError("disk full")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "pretalx.agenda.management.commands.export_schedule_html.export_event",
            failing_export,
        )
        with pytest.raises(CommandError, match="Export failed: disk full"):
            call_command("export_schedule_html", event.slug)


@pytest.mark.django_db
def test_export_schedule_html_command_requires_event_argument():
    with pytest.raises(
        CommandError, match="the following arguments are required: event"
    ):
        call_command("export_schedule_html")


@pytest.mark.django_db
def test_export_schedule_html_command_rejects_unknown_event():
    with pytest.raises(
        CommandError, match='Could not find event with slug "nonexistent"'
    ):
        call_command("export_schedule_html", "nonexistent")
