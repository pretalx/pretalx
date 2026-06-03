# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django_tables2 as tables
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from pretalx.common.tables import BaseTable, SortableColumn
from pretalx.submission.enums import AttendeeSignupStates
from pretalx.submission.models import AttendeeSignup


class AttendeeSignupTable(BaseTable):
    name = SortableColumn(
        verbose_name=_("Name"),
        accessor="attendee__user__name",
        order_by=Lower("attendee__user__name"),
    )
    state = tables.Column(verbose_name=pgettext_lazy("attendee signup state", "State"))

    empty_text = _("No attendees have signed up for this session yet.")

    def render_name(self, record):
        return record.attendee.user.get_display_name()

    def render_state(self, value):
        return dict(AttendeeSignupStates.choices).get(value, value)

    class Meta:
        model = AttendeeSignup
        fields = ("name", "state")
        row_attrs = {"class": lambda record: f"signup-{record.state}"}
