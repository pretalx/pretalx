# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.mail.enums import QueuedMailStates


def _list_base_queryset(event):
    return (
        event.queued_mails.prefetch_users(event)
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
