# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import logging
import tempfile
from pathlib import Path

from django.core.files import File
from django.core.files.storage import default_storage
from django_scopes import scope, scopes_disabled

from pretalx.celery_app import app

logger = logging.getLogger(__name__)


@app.task(name="pretalx.process_image")
def task_process_image(
    *, model: str, pk: int, field: str, generate_thumbnail: bool, name=None
):
    from pretalx.common.image import get_image_for_model, process_image  # noqa: PLC0415 -- leaf

    image = get_image_for_model(model=model, pk=pk, field=field)
    if not image or (name is not None and image.name != name):
        return
    try:
        with scopes_disabled():
            process_image(image=image, generate_thumbnail=generate_thumbnail)
    except (OSError, SyntaxError, ValueError):
        logger.exception("Could not process image %s", image.path)


@app.task(name="pretalx.generate_thumbnails")
def task_generate_thumbnails(*, model: str, pk: int, field: str):
    from pretalx.common.image import (  # noqa: PLC0415 -- leaf
        THUMBNAIL_SIZES,
        create_thumbnail,
        get_image_for_model,
    )

    image = get_image_for_model(model=model, pk=pk, field=field)
    if not image:
        return
    for size in THUMBNAIL_SIZES:
        try:
            with scopes_disabled():
                create_thumbnail(image, size)
        except (OSError, SyntaxError, ValueError):
            logger.exception(
                "Could not regenerate %s thumbnail for %s", size, image.path
            )


@app.task(name="pretalx.cleanup_file")
def task_cleanup_file(*, model: str, pk, field: str, path: str):
    from pretalx.common.models.file import CachedFile  # noqa: PLC0415 -- leaf
    from pretalx.event.models import Event  # noqa: PLC0415 -- leaf
    from pretalx.person.models import ProfilePicture, SpeakerInformation, User  # noqa: PLC0415 -- leaf
    from pretalx.submission.models import Answer, Resource, Submission  # noqa: PLC0415 -- leaf

    models = {
        "Answer": Answer,
        "Cachedfile": CachedFile,
        "Event": Event,
        "Profilepicture": ProfilePicture,
        "Resource": Resource,
        "Speakerinformation": SpeakerInformation,
        "Submission": Submission,
        "User": User,
    }
    if model not in models:
        return

    with scopes_disabled():
        # The instance may be deleted, or have switched to a different file.
        # In both cases we want to delete the actual file.
        instance = models[model].objects.filter(pk=pk).first()
        if instance:
            file = getattr(instance, field, None)
            if file and file.path == path:
                return

        real_path = Path(path)
        if real_path.exists():
            try:
                default_storage.delete(path)
            except OSError:
                logger.exception("Deleting file %s failed.", path)


@app.task(name="pretalx.export_table")
def task_export_table(*, event_id: int, user_id: int, cached_file_id: str, config):
    from pretalx.common.models.file import CachedFile  # noqa: PLC0415 -- leaf
    from pretalx.common.tables.export import ExportError, render_export  # noqa: PLC0415 -- leaf
    from pretalx.event.models import Event  # noqa: PLC0415 -- leaf
    from pretalx.person.models import User  # noqa: PLC0415 -- leaf

    with scopes_disabled():
        event = Event.objects.filter(pk=event_id).first()
        user = User.objects.filter(pk=user_id).first()
        cached_file = CachedFile.objects.filter(id=cached_file_id).first()
    if not event or not user or not cached_file:
        logger.error(
            "Could not export table: event %s, user %s, file %s.",
            event_id,
            user_id,
            cached_file_id,
        )
        return None

    with scope(event=event), tempfile.TemporaryFile() as tmp:
        try:
            render_export(event, user, config, tmp)
        except ExportError:
            logger.exception("Could not export table for event %s.", event.slug)
            return None
        tmp.seek(0)
        cached_file.file.save(cached_file.filename, File(tmp))
    return cached_file_id
