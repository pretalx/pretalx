# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django_tables2 as tables
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables import ActionsColumn, PretalxTable, UnsortableMixin
from pretalx.schedule.models import Room


class RoomTable(UnsortableMixin, PretalxTable):
    default_columns = ("name",)

    name = tables.Column(
        linkify=lambda record: record.urls.settings_base,
        verbose_name=_("Name"),
    )
    capacity = tables.Column(
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}},
    )
    actions = ActionsColumn(
        actions={
            "sort": {},
            "edit": {"url": "urls.settings_base"},
            "delete": {},
        }
    )
    empty_text = _("Please add at least one place in which sessions can take place.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attrs["dragsort-url"] = self.event.orga_urls.room_settings

    class Meta:
        model = Room
        fields = (
            "name",
            "capacity",
            "guid",
        )
        row_attrs = {"dragsort-id": lambda record: record.pk}
