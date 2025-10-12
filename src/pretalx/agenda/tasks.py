# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: luto

import logging

from django_scopes import scope, scopes_disabled

from pretalx.celery_app import app
from pretalx.event.models import Event

LOGGER = logging.getLogger(__name__)


@app.task(name="pretalx.agenda.export_schedule_html")
def export_schedule_html(*, event_id: int, make_zip=True):
    from django.core.management import call_command

    with scopes_disabled():
        event = (
            Event.objects.prefetch_related("submissions").filter(pk=event_id).first()
        )
    if not event:
        LOGGER.error(f"Could not find Event ID {event_id} for export.")
        return

    with scope(event=event):
        if not event.current_schedule:
            LOGGER.error(
                f"Event {event.slug} could not be exported: it has no schedule."
            )
            return

    cmd = ["export_schedule_html", event.slug]
    if make_zip:
        cmd.append("--zip")
    call_command(*cmd)
