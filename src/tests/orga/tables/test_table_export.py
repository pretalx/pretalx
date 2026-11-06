# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.orga.tables.table_export import TableExportTable
from tests.factories import TableExportFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_table_export_table_renders_summary_and_table_name(event):
    export = TableExportFactory(
        event=event,
        columns=["title", "state"],
        filters={"state": ["accepted"]},
        ordering=["title"],
    )
    stale = TableExportFactory(event=event, table="GoneTable", columns=[])
    table = TableExportTable([export, stale], event=event, user=UserFactory.build())

    assert table.render_table(export) == "Sessions"
    assert table.render_serializer("csv") == "CSV"
    assert table.render_serializer("xlsx") == "xlsx"
    assert table.render_summary(export).count(",") == 2
    assert "2" in table.render_summary(export)
    assert table.render_summary(stale).count(",") == 0
    assert table.exportable is False
