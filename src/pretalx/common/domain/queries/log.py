# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.prefetch import GenericPrefetch

from pretalx.common.models import ActivityLog


def generic_event_prefetch():
    from pretalx.submission.models import Answer  # noqa: PLC0415 -- circular import

    models = [
        model
        for model in apps.get_models()
        if any(
            field.name == "event" and field.is_relation for field in model._meta.fields
        )
    ]
    ContentType.objects.get_for_models(Answer, *models)
    querysets = [model._base_manager.select_related("event__cfp") for model in models]
    querysets.append(Answer._base_manager.select_related("question__event"))
    return GenericPrefetch("content_object", querysets)


def actions_by(person):
    return (
        ActivityLog.objects.filter(person=person)
        .select_related("event")
        .prefetch_related("person", generic_event_prefetch())
    )


def event_activity_log(event):
    return (
        ActivityLog.objects.filter(event=event)
        .select_related("person", "content_type", "event")
        .prefetch_related(generic_event_prefetch())
    )
