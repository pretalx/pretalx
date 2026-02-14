# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: luto

import logging

from django.core.files import File
from django_scopes import scope, scopes_disabled

from pretalx.agenda.management.commands.export_schedule_html import get_export_zip_path
from pretalx.celery_app import app
from pretalx.common.models.file import CachedFile
from pretalx.event.models import Event


LOGGER = logging.getLogger(__name__)


@app.task(name="pretalx.agenda.export_schedule_html")
def export_schedule_html(*, event_id, cached_file_id=None):
    from django.core.management import call_command  # noqa: PLC0415

    with scopes_disabled():
        event = (
            Event.objects.prefetch_related("submissions").filter(pk=event_id).first()
        )
    if not event:
        LOGGER.error("Could not find Event ID %s for export.", event_id)
        return

    with scope(event=event):
        if not event.current_schedule:
            LOGGER.error(
                "Event %s could not be exported: it has no schedule.", event.slug
            )
            return

    cmd = ["export_schedule_html", event.slug, "--zip"]
    call_command(*cmd)

    if cached_file_id:
        cached_file = CachedFile.objects.filter(id=cached_file_id).first()
        if cached_file:
            zip_path = get_export_zip_path(event)
            try:
                with zip_path.open("rb") as f:
                    cached_file.file.save(cached_file.filename, File(f))
                zip_path.unlink(missing_ok=True)
            except FileNotFoundError:
                LOGGER.error("Export zip not found at %s", zip_path)
                return
            return cached_file_id
