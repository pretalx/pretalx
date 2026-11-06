# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.orga.tables.submission import SubmissionTable
from tests.factories import TableExportFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_table_export_config_table_class_and_urls(event):
    export = TableExportFactory(
        event=event,
        name="Talks",
        columns=["title"],
        ordering=["-title"],
        filters={"state": ["accepted"]},
        serializer_options={"list_delimiter": "comma"},
        locale="",
    )
    stale = TableExportFactory(event=event, table="GoneTable")

    assert str(export) == "Talks"
    assert export.table_class is SubmissionTable
    assert export.log_parent == event
    assert export.config == {
        "table": "SubmissionTable",
        "columns": ["title"],
        "ordering": ["-title"],
        "filters": {"state": ["accepted"]},
        "serializer": "csv",
        "locale": None,
        "serializer_options": {"list_delimiter": "comma"},
    }
    assert export.urls.edit == f"{event.orga_urls.exports}{export.pk}/"
    assert export.urls.delete == f"{event.orga_urls.exports}{export.pk}/delete/"
    assert export.urls.run == f"{event.orga_urls.exports}{export.pk}/run/"
    assert stale.table_class is None
