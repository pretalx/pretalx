# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from freezegun import freeze_time

from pretalx.orga.views.exports import (
    AdhocTableExportRun,
    MoreExportsView,
    TableExportRun,
    usable_export_tables,
)
from tests.factories import EventFactory, TableExportFactory
from tests.utils import make_orga_user, make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_usable_export_tables_follow_permissions(event):
    orga = make_orga_user(event, can_change_submissions=True)
    reviewer = make_orga_user(event, is_reviewer=True, can_change_submissions=False)

    orga_names = {cls.__name__ for cls in usable_export_tables(event, orga)}
    reviewer_names = {cls.__name__ for cls in usable_export_tables(event, reviewer)}

    assert "OutboxMailTable" in orga_names
    assert "OutboxMailTable" not in reviewer_names
    assert "SpeakerInformationTable" in orga_names
    assert "SpeakerInformationTable" not in reviewer_names
    assert "ReviewerQuestionTable" not in orga_names
    assert "ReviewerQuestionTable" in {
        cls.__name__
        for cls in usable_export_tables(
            event, make_orga_user(event, can_change_event_settings=True)
        )
    }
    assert {"ReviewTable", "ReviewExportTable", "SubmissionTable"} <= reviewer_names


def test_table_export_run_filename_and_content_type():
    event = EventFactory(timezone="Europe/Berlin")
    user = make_orga_user(event, can_change_event_settings=True)
    export = TableExportFactory(event=event, name="Café Talks!", serializer="json")
    request = make_request(event, user=user)
    view = make_view(TableExportRun, request, pk=export.pk)
    view.export_config = export.config

    with freeze_time("2026-11-06 13:05:00"):
        filename = view.get_async_download_filename()

    assert filename == f"{event.slug}_cafe-talks_2026-11-06_14-05.json"
    assert view.get_async_download_content_type() == "application/json"
    assert view.get_error_redirect_url() == event.orga_urls.exports


def test_table_export_run_filename_from_table_name(event):
    user = make_orga_user(event, can_change_submissions=True)
    request = make_request(event, user=user, method="post")
    request.POST = {"table": "SubmissionTable"}
    view = make_view(AdhocTableExportRun, request)
    view.export_config = {"serializer": "csv"}

    with freeze_time("2026-11-06 13:05:00"):
        filename = view.get_async_download_filename()

    assert filename == f"{event.slug}_sessions_2026-11-06_13-05.csv"
    assert view.get_error_redirect_url() == event.orga_urls.base
    assert view.get_back_url() == event.orga_urls.base


def test_more_exports_view_partitions_exporters_without_release(event):
    user = make_orga_user(event, can_change_event_settings=True)
    view = make_view(MoreExportsView, make_request(event, user=user))

    available = {exporter.identifier for exporter in view.available_exporters}
    unavailable = {exporter.identifier for exporter in view.unavailable_exporters}

    assert "speakers.csv" in available
    assert {"schedule.xml", "schedule.ics"} <= unavailable
    assert not available & unavailable
    assert [(button.label, button.color) for button in view.zip_buttons] == [
        ("Regenerate Export", "secondary"),
        ("Download ZIP", "primary"),
    ]


def test_more_exports_view_all_exporters_available_after_release(published_talk_slot):
    event = published_talk_slot.submission.event
    user = make_orga_user(event, can_change_event_settings=True)
    view = make_view(MoreExportsView, make_request(event, user=user))

    available = {exporter.identifier for exporter in view.available_exporters}

    assert {"schedule.xml", "schedule.ics", "speakers.csv"} <= available
    assert view.unavailable_exporters == []
