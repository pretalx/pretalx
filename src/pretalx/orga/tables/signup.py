# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django_tables2 as tables
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from pretalx.common.tables import DateTimeColumn, PretalxTable, SortableColumn
from pretalx.submission.enums import AttendeeSignupStates
from pretalx.submission.models import AttendeeSignup


class AttendeeSignupTable(PretalxTable):
    name = SortableColumn(
        verbose_name=_("Name"),
        accessor="attendee__user__name",
        order_by=Lower("attendee__user__name"),
    )
    email = SortableColumn(
        verbose_name=_("Email"),
        accessor="attendee__user__email",
        order_by=Lower("attendee__user__email"),
    )
    state = tables.Column(verbose_name=_("State"))
    position = tables.Column(
        verbose_name=_("Position"),
        attrs={"th": {"class": "numeric"}, "td": {"class": "numeric text-center"}},
    )
    created = DateTimeColumn(verbose_name=_("Signed up at"))

    default_columns = ("name", "email", "state")
    empty_text = _("No attendees have signed up for this session yet.")

    def render_state(self, value, record):
        return dict(AttendeeSignupStates.choices).get(value, value)

    class Meta:
        model = AttendeeSignup
        fields = ("name", "email", "state", "position", "created")
