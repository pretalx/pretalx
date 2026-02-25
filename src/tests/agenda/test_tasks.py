from unittest.mock import patch

import pytest
from django.conf import settings

from pretalx.agenda.tasks import export_schedule_html
from tests.factories import CachedFileFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_export_schedule_html_nonexistent_event():
    result = export_schedule_html(event_id=99999)

    assert result is None


@pytest.mark.django_db
def test_export_schedule_html_no_schedule(event):
    """Event with no published schedule returns None."""
    result = export_schedule_html(event_id=event.pk)

    assert result is None


@pytest.mark.django_db
def test_export_schedule_html_without_cached_file(published_schedule):
    """Task returns None when no cached_file_id is provided."""
    with patch("django.core.management.call_command"):
        result = export_schedule_html(event_id=published_schedule.event.pk)

    assert result is None


@pytest.mark.django_db
def test_export_schedule_html_with_cached_file(published_schedule):
    """Task saves zip to CachedFile and returns its ID."""
    event = published_schedule.event
    cached_file = CachedFileFactory(filename="export.zip")

    zip_path = settings.HTMLEXPORT_ROOT / f"{event.slug}.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    zip_path.write_bytes(b"PK\x03\x04fake-zip-content")

    with patch("django.core.management.call_command"):
        result = export_schedule_html(
            event_id=event.pk, cached_file_id=str(cached_file.id)
        )

    assert result == str(cached_file.id)
    cached_file.refresh_from_db()
    assert cached_file.file
    assert not zip_path.exists()


@pytest.mark.django_db
def test_export_schedule_html_cached_file_not_found(published_schedule):
    """Task returns None when cached_file_id points to a nonexistent CachedFile."""
    with patch("django.core.management.call_command"):
        result = export_schedule_html(
            event_id=published_schedule.event.pk,
            cached_file_id="00000000-0000-0000-0000-000000000000",
        )

    assert result is None


@pytest.mark.django_db
def test_export_schedule_html_zip_missing(published_schedule):
    """Task returns None when the zip file doesn't exist on disk."""
    cached_file = CachedFileFactory(filename="export.zip")

    with patch("django.core.management.call_command"):
        result = export_schedule_html(
            event_id=published_schedule.event.pk, cached_file_id=str(cached_file.id)
        )

    assert result is None
