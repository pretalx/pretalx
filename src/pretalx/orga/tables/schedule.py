# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django_tables2 as tables
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables import ActionsColumn, DragsortTable
from pretalx.schedule.domain.room import ROOM_IN_USE_ERROR
from pretalx.schedule.models import Room


class RoomTable(DragsortTable):
    default_columns = ("name",)

    name = tables.Column(
        linkify=lambda record: record.urls.settings_base,
        verbose_name=_("Name"),
        attrs={
            "td": {"class": lambda record: "room-hidden-name" if record.hidden else ""}
        },
    )
    capacity = tables.Column(
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric"}}
    )
    actions = ActionsColumn(
        actions={
            "sort": {"condition": lambda record: not record.hidden},
            "edit": {"url": "urls.settings_base"},
            "delete": {
                "condition": lambda record: not record.hidden and record.is_deletable
            },
            "hide": {
                "title": _("Hide room"),
                "icon": "eye-slash",
                "url": "urls.hide",
                "color": "warning",
                "permission": "update",
                "condition": lambda record: (
                    not record.hidden
                    and not record.is_deletable
                    and not record.is_in_use
                ),
            },
            "blocked": {
                "title": ROOM_IN_USE_ERROR,
                "icon": "trash",
                "color": "danger",
                "extra_class": "disabled",
                "extra_attrs": 'aria-disabled="true"',
                "permission": "update",
                "condition": lambda record: not record.hidden and record.is_in_use,
            },
            "unhide": {
                "title": _("Make visible"),
                "icon": "eye",
                "url": "urls.unhide",
                "color": "outline-danger",
                "permission": "update",
                "condition": lambda record: record.hidden,
            },
        }
    )

    def get_dragsort_url(self):
        return self.event.orga_urls.room_settings

    class Meta:
        model = Room
        fields = ("name", "capacity", "guid")
        row_attrs = {"class": lambda record: "room-hidden" if record.hidden else ""}
        empty_text = _(
            "Please add at least one place in which sessions can take place."
        )
