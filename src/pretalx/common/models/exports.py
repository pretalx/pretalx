# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from pretalx.common.models.mixins import PretalxModel
from pretalx.common.urls import EventUrls
from pretalx.event.rules import can_change_event_settings


class TableExport(PretalxModel):
    """A named, event-scoped table export configuration."""

    event = models.ForeignKey(
        to="event.Event", on_delete=models.CASCADE, related_name="table_exports"
    )
    name = models.CharField(max_length=200, verbose_name=_("Name"))
    table = models.CharField(max_length=100)
    columns = models.JSONField(default=list, blank=True)
    ordering = models.JSONField(default=list, blank=True)
    filters = models.JSONField(default=dict, blank=True)
    serializer = models.CharField(max_length=20, verbose_name=_("Export format"))
    serializer_options = models.JSONField(default=dict, blank=True)

    log_prefix = "pretalx.table_export"

    class Meta:
        ordering = ("name", "pk")
        rules_permissions = {
            "list": can_change_event_settings,
            "view": can_change_event_settings,
            "create": can_change_event_settings,
            "update": can_change_event_settings,
            "delete": can_change_event_settings,
        }

    class urls(EventUrls):
        base = edit = "{self.event.orga_urls.exports}{self.pk}/"
        delete = "{base}delete/"
        run = "{base}run/"

    def __str__(self):
        return self.name

    @property
    def log_parent(self):
        return self.event

    @cached_property
    def table_class(self):
        from pretalx.common.tables.export import get_exportable_table  # noqa: PLC0415 -- thin method

        return get_exportable_table(self.event, self.table)

    @property
    def config(self):
        return {
            "table": self.table,
            "columns": list(self.columns or []),
            "ordering": list(self.ordering or []),
            "filters": dict(self.filters or {}),
            "serializer": self.serializer,
            "serializer_options": dict(self.serializer_options or {}),
        }
