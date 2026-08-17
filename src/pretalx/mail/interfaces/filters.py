# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Count, Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from pretalx.common.tables.filters import (
    FilterChoice,
    ModelMultiChoiceFilter,
    MultiChoiceFilter,
    SearchFilter,
)
from pretalx.mail.domain.queries import draft_mail_counts, search_mails
from pretalx.mail.enums import QueuedMailStates


class MailStatusFilter(MultiChoiceFilter):
    def get_choices(self):
        if not self.event:
            return []
        counts = draft_mail_counts(self.event)
        failed = counts["failed_count"]
        if not failed:
            return []
        return [
            FilterChoice(
                "draft",
                pgettext_lazy("email status: not yet sent", "Pending"),
                count=counts["pending_count"] - failed,
            ),
            FilterChoice(
                "failed", pgettext_lazy("email status", "Failed"), count=failed
            ),
        ]


class MailTrackFilter(ModelMultiChoiceFilter):
    def is_available(self):
        return bool(self.event and self.event.has_active_tracks)

    def get_queryset(self):
        mail_filter = Q(submissions__mails__event=self.event)
        if self.context.get("sent"):
            mail_filter &= Q(
                submissions__mails__state__in=[
                    QueuedMailStates.SENT,
                    QueuedMailStates.SENDING,
                ]
            )
        else:
            mail_filter &= Q(submissions__mails__state=QueuedMailStates.DRAFT)
        return self.event.tracks.annotate(
            mail_count=Count("submissions__mails", distinct=True, filter=mail_filter)
        ).order_by("-mail_count")


def queued_mail_filters(context):
    filters = [SearchFilter(search=search_mails)]
    if not context.get("sent"):
        filters.append(
            MailStatusFilter(
                name="status",
                field="computed_state",
                label=pgettext_lazy("email delivery status", "Status"),
                with_counts=True,
            )
        )
    filters.append(
        MailTrackFilter(
            name="track",
            field="submissions__track",
            label=_("Tracks"),
            with_counts=True,
            count_attr="mail_count",
            distinct=True,
        )
    )
    return filters
