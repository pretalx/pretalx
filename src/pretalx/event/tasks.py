# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django_scopes import scope, scopes_disabled

from pretalx.celery_app import app


@app.task(name="pretalx.event.periodic_event_services")
def task_periodic_event_services(event_slug):
    from pretalx.event.domain.lifecycle import (  # noqa: PLC0415 -- leaf
        send_lifecycle_notifications,
    )
    from pretalx.event.models import Event  # noqa: PLC0415 -- leaf

    with scopes_disabled():
        event = (
            Event.objects.filter(slug=event_slug)
            .select_related("cfp")
            .prefetch_related(
                "_settings_objects",
                "submissions__slots",
                "schedules",
                "review_phases",
                "score_categories",
            )
            .first()
        )
    if not event:
        return

    with scope(event=event):
        send_lifecycle_notifications(event)
