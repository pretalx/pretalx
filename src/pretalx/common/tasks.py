# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import logging
from pathlib import Path

from django.core.files.storage import default_storage
from django_scopes import scopes_disabled

from pretalx.celery_app import app

logger = logging.getLogger(__name__)


@app.task(name="pretalx.process_image")
def task_process_image(*, model: str, pk: int, field: str, generate_thumbnail: bool):
    from pretalx.common.image import (  # noqa: PLC0415 -- leaf
        get_image_for_model,
        process_image,
    )

    image = get_image_for_model(model=model, pk=pk, field=field)
    if not image:
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
    from pretalx.person.models import (  # noqa: PLC0415 -- leaf
        ProfilePicture,
        SpeakerInformation,
        User,
    )
    from pretalx.submission.models import (  # noqa: PLC0415 -- leaf
        Answer,
        Resource,
        Submission,
    )

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
