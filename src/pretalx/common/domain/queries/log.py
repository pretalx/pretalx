# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.contrib.contenttypes.prefetch import GenericPrefetch

from pretalx.common.models import ActivityLog


def actions_by(person):
    """All :class:`ActivityLog` rows whose actor is ``person``."""
    return ActivityLog.objects.filter(person=person).select_related("event")


def event_activity_log(event):
    return (
        ActivityLog.objects.filter(event=event)
        .select_related("person", "content_type", "event")
        .prefetch_related(
            GenericPrefetch(
                "content_object", [event.submissions.select_related("event")]
            )
        )
    )
