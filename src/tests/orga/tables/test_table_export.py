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
    stale = TableExportFactory(
        event=event, table="GoneTable", columns=[], filters={"state": ["accepted"]}
    )
    table = TableExportTable([export, stale], event=event, user=UserFactory())

    assert table.render_table(export) == "Sessions"
    assert table.render_serializer("csv") == "CSV"
    assert table.render_serializer("pdf") == "pdf"
    assert table.render_summary(export).count(",") == 2
    assert "2" in table.render_summary(export)
    assert table.render_summary(stale) == "0 columns, 1 filters"
    assert table.exportable is False


@pytest.mark.parametrize(
    ("filters", "expected"),
    (
        ({"state": ["submitted", "accepted", "confirmed"]}, ""),
        ({"state": ["accepted", "submitted", "confirmed"], "track": [1]}, "1 filters"),
        ({"state": ["accepted"]}, "1 filters"),
        ({"state": "accepted"}, "1 filters"),
    ),
    ids=("defaults_only", "default_plus_one", "changed_default", "scalar_value"),
)
def test_table_export_summary_counts_only_non_default_filters(
    event, filters, expected, django_assert_num_queries
):
    export = TableExportFactory(event=event, filters=filters)
    other = TableExportFactory(event=event, filters=filters)
    table = TableExportTable([export, other], event=event, user=UserFactory())

    with django_assert_num_queries(1):
        summary = table.render_summary(export)
        table.render_summary(other)

    assert summary == f"2 columns, {expected}".rstrip(", ")
