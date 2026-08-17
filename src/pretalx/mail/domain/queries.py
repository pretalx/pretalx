# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Count, Q

from pretalx.mail.enums import QueuedMailStates
from pretalx.submission.domain.queries.submission import speaker_search_q


def search_mails(qs, query, fulltext=False, context=None):
    return qs.filter(
        Q(to__icontains=query)
        | Q(subject__icontains=query)
        | speaker_search_q(query, prefix="to_speakers__")
    ).distinct()


def draft_mail_counts(event):
    """Dict of {"pending_count": …, "failed_count": …}."""
    return event.queued_mails.filter(state=QueuedMailStates.DRAFT).aggregate(
        pending_count=Count("pk"),
        failed_count=Count("pk", filter=Q(error_data__isnull=False)),
    )


def _list_base_queryset(event):
    return (
        event.queued_mails.prefetch_recipients(event)
        .prefetch_related("submissions", "submissions__track", "submissions__event")
        .select_related("template")
    )


def outbox_mails(event):
    return (
        _list_base_queryset(event)
        .filter(state=QueuedMailStates.DRAFT)
        .with_computed_state()
        .order_by("-id")
    )


def sent_mails(event):
    return (
        _list_base_queryset(event)
        .filter(state__in=[QueuedMailStates.SENT, QueuedMailStates.SENDING])
        .with_computed_state()
        .order_by("-sent")
    )
