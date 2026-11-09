# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django_tables2 as tables
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from pretalx.common.models.exports import TableExport
from pretalx.common.tables import ActionsColumn, PretalxTable
from pretalx.common.tables.export import build_filterset, get_table_serializers


def _as_values(value):
    if isinstance(value, (list, tuple, set, frozenset)):
        return sorted(str(entry) for entry in value)
    return [str(value)]


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
                "title": _("Download data"),
                "icon": "download",
                "url": "urls.run",
                "color": "primary",
            },
            "view": {
                "title": _("View data"),
                "icon": "table",
                "url": "view_data_url",
                "condition": lambda record: record.view_data_url,
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

    @cached_property
    def filter_defaults(self):
        return {}

    def get_filter_defaults(self, table_class):
        if table_class is None:
            return {}
        if table_class.__name__ not in self.filter_defaults:
            filterset = build_filterset(table_class, self.event, self.user, {})
            defaults = {}
            for table_filter in filterset.filters.values() if filterset else ():
                initial = table_filter.get_initial()
                if initial is not None:
                    defaults[table_filter.param] = _as_values(initial)
            self.filter_defaults[table_class.__name__] = defaults
        return self.filter_defaults[table_class.__name__]

    def count_filters(self, record):
        if not record.filters:
            return 0
        defaults = self.get_filter_defaults(record.table_class)
        return sum(
            1
            for param, values in record.filters.items()
            if _as_values(values) != defaults.get(param)
        )

    def render_summary(self, record):
        parts = [_("{count} columns").format(count=len(record.columns or []))]
        if filter_count := self.count_filters(record):
            parts.append(_("{count} filters").format(count=filter_count))
        if record.ordering:
            parts.append(_("sorted"))
        return ", ".join(str(part) for part in parts)

    class Meta:
        model = TableExport
        fields = ("name", "table", "serializer", "summary", "actions")
