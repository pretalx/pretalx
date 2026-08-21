# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.apps import apps
from django.contrib.contenttypes.prefetch import GenericPrefetch

from pretalx.common.models import ActivityLog


def actions_by(person):
    event_aware_querysets = [
        model._base_manager.select_related("event")
        for model in apps.get_models()
        if any(
            field.name == "event" and field.is_relation for field in model._meta.fields
        )
    ]
    return (
        ActivityLog.objects.filter(person=person)
        .select_related("event")
        .prefetch_related(
            "person", GenericPrefetch("content_object", event_aware_querysets)
        )
    )


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
