# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django_scopes import scope

from pretalx.celery_app import app


@app.task(name="pretalx.schedule.update_unreleased_schedule_changes")
def task_update_unreleased_schedule_changes(event=None, value=None):
    from pretalx.event.models import Event
    from pretalx.schedule.services import update_unreleased_schedule_changes

    event = Event.objects.get(slug=event)
    with scope(event=event):
        update_unreleased_schedule_changes(event=event, value=value)
