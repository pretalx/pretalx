# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.prefetch import GenericPrefetch

from pretalx.common.models import ActivityLog
from pretalx.event.models import Event
from pretalx.person.models import User
from pretalx.submission.models import Question, Submission


def generic_event_prefetch():
    qualifying_paths = {
        "event": (Event, "event__cfp"),
        "submission": (Submission, "submission__event__cfp"),
        "question": (Question, "question__event__cfp"),
    }
    supplementary_paths = {"user": (User, "user")}

    models = []
    querysets = []
    for model in apps.get_models():
        targets = {
            field.name: field.related_model
            for field in model._meta.fields
            if field.is_relation
        }
        paths = [
            path
            for name, (target, path) in qualifying_paths.items()
            if targets.get(name) is target
        ]
        if not paths:
            continue
        paths += [
            path
            for name, (target, path) in supplementary_paths.items()
            if targets.get(name) is target
        ]
        models.append(model)
        querysets.append(model._base_manager.select_related(*paths))
    ContentType.objects.get_for_models(*models)
    return GenericPrefetch("content_object", querysets)


def actions_by(person):
    return (
        ActivityLog.objects.filter(person=person)
        .select_related("event")
        .prefetch_related("person__profile_picture", generic_event_prefetch())
    )


def event_activity_log(event):
    return (
        ActivityLog.objects.filter(event=event)
        .select_related("person__profile_picture", "event")
        .prefetch_related(generic_event_prefetch())
    )
