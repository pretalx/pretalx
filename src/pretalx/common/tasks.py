# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import logging
from pathlib import Path

from django.core.files.storage import default_storage
from django_scopes import scopes_disabled

from pretalx.celery_app import app
from pretalx.common.image import THUMBNAIL_SIZES, create_thumbnail, process_image
from pretalx.event.models import Event
from pretalx.person.models import ProfilePicture, SpeakerInformation, User
from pretalx.submission.models import Answer, Resource, Submission

logger = logging.getLogger(__name__)

IMAGE_MODELS = {
    "Event": Event,
    "Profilepicture": ProfilePicture,
    "Submission": Submission,
    "User": User,
}


@app.task(name="pretalx.process_image")
def task_process_image(*, model: str, pk: int, field: str, generate_thumbnail: bool):
    if model not in IMAGE_MODELS:
        return

    with scopes_disabled():
        instance = IMAGE_MODELS[model].objects.filter(pk=pk).first()
        if not instance:
            return

        image = getattr(instance, field, None)
        if not image:
            return

        try:
            process_image(image=image, generate_thumbnail=generate_thumbnail)
        except (OSError, SyntaxError, ValueError):
            logger.exception("Could not process image %s", image.path)


@app.task(name="pretalx.generate_thumbnails")
def task_generate_thumbnails(*, model: str, pk: int, field: str):
    if model not in IMAGE_MODELS:
        return

    with scopes_disabled():
        instance = IMAGE_MODELS[model].objects.filter(pk=pk).first()
        if not instance:
            return

        image = getattr(instance, field, None)
        if not image:
            return

        for size in THUMBNAIL_SIZES:
            try:
                create_thumbnail(image, size)
            except (OSError, SyntaxError, ValueError):
                logger.exception(
                    "Could not regenerate %s thumbnail for %s", size, image.path
                )


@app.task(name="pretalx.cleanup_file")
def task_cleanup_file(*, model: str, pk: int, field: str, path: str):
    models = {
        "Answer": Answer,
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
        instance = models[model].objects.filter(pk=pk).first()
        if not instance:
            return

        file = getattr(instance, field, None)
        if file and file.path == path:
            # The save action that triggered this task did not go through and the file
            # is still in use, so we should not delete it.
            return

        real_path = Path(path)
        if real_path.exists():
            try:
                default_storage.delete(path)
            except OSError:
                logger.exception("Deleting file %s failed.", path)
