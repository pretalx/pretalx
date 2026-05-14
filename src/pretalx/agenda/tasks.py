# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: luto

import logging

from django.core.files import File
from django_scopes import scope, scopes_disabled

from pretalx.celery_app import app

LOGGER = logging.getLogger(__name__)


@app.task(name="pretalx.agenda.export_schedule_html")
def task_export_schedule_html(*, event_id, cached_file_id=None):
    from pretalx.agenda.html_export import (  # noqa: PLC0415 -- slow import
        export_event_html,
        get_export_zip_path,
    )
    from pretalx.common.models.file import CachedFile  # noqa: PLC0415 -- leaf
    from pretalx.event.models import Event  # noqa: PLC0415 -- leaf

    with scopes_disabled():
        event = (
            Event.objects.prefetch_related("submissions").filter(pk=event_id).first()
        )
    if not event:
        LOGGER.error("Could not find Event ID %s for export.", event_id)
        return None

    with scope(event=event):
        if not event.current_schedule:
            LOGGER.error(
                "Event %s could not be exported: it has no schedule.", event.slug
            )
            return None

    cached_file = CachedFile.objects.filter(id=cached_file_id).first()
    if cached_file_id and not cached_file:
        LOGGER.error("CachedFile %s could not be found.", cached_file_id)
        return None

    export_event_html(event, as_zip=True)

    if cached_file:
        zip_path = get_export_zip_path(event)
        try:
            with zip_path.open("rb") as f:
                cached_file.file.save(cached_file.filename, File(f))
            zip_path.unlink(missing_ok=True)
        except FileNotFoundError:
            LOGGER.exception("Export zip not found at %s", zip_path)
            return None
        return cached_file_id
