# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django_tables2 as tables
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from pretalx.common.models.exports import TableExport
from pretalx.common.tables import ActionsColumn, PretalxTable
from pretalx.common.tables.export import get_table_serializers


class TableExportTable(PretalxTable):
    primary_column = "name"
    default_columns = ("name", "table", "serializer", "summary")

    name = tables.Column(linkify=lambda record: record.urls.edit)
    table = tables.Column(verbose_name=_("Table"), orderable=False, empty_values=())
    serializer = tables.Column(verbose_name=_("Export format"))
    summary = tables.Column(
        verbose_name=_("Configuration"), orderable=False, empty_values=()
    )
    actions = ActionsColumn(
        actions={
            "run": {
                "title": _("Run export"),
                "icon": "download",
                "url": "urls.run",
                "color": "primary",
            },
            "edit": {},
            "delete": {},
        }
    )

    def render_table(self, record):
        return record.table_class.export_name

    @cached_property
    def serializers(self):
        return get_table_serializers(self.event)

    def render_serializer(self, value):
        serializer = self.serializers.get(value)
        return serializer.verbose_name if serializer else value

    def render_summary(self, record):
        parts = [_("{count} columns").format(count=len(record.columns or []))]
        if record.filters:
            parts.append(_("{count} filters").format(count=len(record.filters)))
        if record.ordering:
            parts.append(_("sorted"))
        return ", ".join(str(part) for part in parts)

    class Meta:
        model = TableExport
        fields = ("name", "table", "serializer", "summary", "actions")
