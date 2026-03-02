# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from pathlib import Path

import pytest
from django.conf import settings

from pretalx.agenda.tasks import export_schedule_html
from tests.factories import CachedFileFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_export_schedule_html_nonexistent_event():
    result = export_schedule_html(event_id=99999)

    assert result is None


def test_export_schedule_html_no_schedule(event):
    result = export_schedule_html(event_id=event.pk)

    assert result is None


def test_export_schedule_html_cached_file_not_found(published_talk_slot):
    result = export_schedule_html(
        event_id=published_talk_slot.submission.event.pk,
        cached_file_id="00000000-0000-0000-0000-000000000000",
    )

    assert result is None


@pytest.mark.filterwarnings(
    "ignore:It looks like you're using an HTML parser to parse an XML document"
)
def test_export_schedule_html_without_cached_file(published_talk_slot):
    result = export_schedule_html(event_id=published_talk_slot.submission.event.pk)

    assert result is None


@pytest.mark.filterwarnings(
    "ignore:It looks like you're using an HTML parser to parse an XML document"
)
def test_export_schedule_html_with_cached_file(published_talk_slot, monkeypatch):
    event = published_talk_slot.submission.event
    cached_file = CachedFileFactory(filename="export.zip")

    result = export_schedule_html(event_id=event.pk, cached_file_id=str(cached_file.id))

    zip_path = settings.HTMLEXPORT_ROOT / f"{event.slug}.zip"
    assert result == str(cached_file.id)
    cached_file.refresh_from_db()
    assert cached_file.file
    assert not zip_path.exists()

    # When the export zip is missing, task returns None
    monkeypatch.setattr(
        "pretalx.agenda.tasks.get_export_zip_path",
        lambda event: Path("/nonexistent/path/export.zip"),
    )
    cached_file2 = CachedFileFactory(filename="export2.zip")
    result = export_schedule_html(
        event_id=event.pk, cached_file_id=str(cached_file2.id)
    )
    assert result is None
