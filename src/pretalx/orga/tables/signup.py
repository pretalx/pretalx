# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django_tables2 as tables
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables import DateTimeColumn, PretalxTable, SortableColumn
from pretalx.submission.interfaces.tables import (
    AttendeeSignupTable as PublicAttendeeSignupTable,
)


class AttendeeSignupTable(PublicAttendeeSignupTable, PretalxTable):
    email = SortableColumn(
        verbose_name=_("Email"),
        accessor="attendee__user__email",
        order_by=Lower("attendee__user__email"),
    )
    position = tables.Column(
        verbose_name=_("Position"),
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric text-center"}},
    )
    created = DateTimeColumn(verbose_name=_("Signed up at"))

    default_columns = ("name", "email", "state")

    class Meta(PublicAttendeeSignupTable.Meta):
        fields = ("name", "email", "state", "position", "created")
