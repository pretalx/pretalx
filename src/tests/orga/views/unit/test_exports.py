# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.orga.views.exports import TableExportRun, usable_export_tables
from tests.factories import TableExportFactory
from tests.utils import make_orga_user, make_request, make_view

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_usable_export_tables_follow_permissions(event):
    orga = make_orga_user(event, can_change_submissions=True)
    reviewer = make_orga_user(event, is_reviewer=True, can_change_submissions=False)

    orga_names = {cls.__name__ for cls in usable_export_tables(event, orga)}
    reviewer_names = {cls.__name__ for cls in usable_export_tables(event, reviewer)}

    assert "OutboxMailTable" in orga_names
    assert "OutboxMailTable" not in reviewer_names
    assert {"ReviewTable", "ReviewExportTable", "SubmissionTable"} <= reviewer_names


def test_table_export_run_filename_and_content_type(event):
    user = make_orga_user(event, can_change_event_settings=True)
    export = TableExportFactory(event=event, name="Café Talks!", serializer="json")
    request = make_request(event, user=user)
    view = make_view(TableExportRun, request, pk=export.pk)
    view.export_config = export.config

    assert view.get_async_download_filename() == f"{event.slug}_cafe-talks.json"
    assert view.get_async_download_content_type() == "application/json"
    assert view.get_error_redirect_url() == event.orga_urls.exports
