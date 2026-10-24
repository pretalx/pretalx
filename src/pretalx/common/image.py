# SPDX-FileCopyrightText: 2024-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import logging
from contextlib import suppress
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django_scopes import scopes_disabled

from pretalx.common.tasks import task_generate_thumbnails
from pretalx.event.models import Event
from pretalx.person.models import ProfilePicture
from pretalx.submission.models import Answer, Submission

logger = logging.getLogger(__name__)

# If we do not limit image types, PIL sniffes file types and loads decoders eagerly,
# which increases attack surface of e.g. decompression bombs.
ALLOWED_IMAGE_FORMATS = ("PNG", "JPEG", "GIF", "WEBP")

THUMBNAIL_SIZES = {"tiny": (64, 64), "default": (460, 460)}


def _open_image(source):
    from PIL import Image  # noqa: PLC0415 -- slow import

    image = Image.open(source, formats=ALLOWED_IMAGE_FORMATS)
    if image.width * image.height > Image.MAX_IMAGE_PIXELS:
        raise Image.DecompressionBombError(
            f"Image size ({image.width * image.height} pixels) exceeds pixel limit"
        )
    return image


def validate_image(f):
    if f is None:
        return

    if hasattr(f, "temporary_file_path"):
        file = f.temporary_file_path()
    elif hasattr(f, "read"):
        if hasattr(f, "seek") and callable(f.seek):
            f.seek(0)
        file = BytesIO(f.read())
    else:
        file = BytesIO(f["content"])

    from PIL import Image  # noqa: PLC0415 -- slow import

    try:
        image = _open_image(file)
        image.verify()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError(
            _(
                "The file you uploaded has a very large number of pixels, please upload a picture with smaller dimensions."
            )
        ) from None
    except Exception as exc:
        raise ValidationError(
            _(
                "Upload a valid image. The file you uploaded was either not an image or a corrupted image."
            )
        ) from exc
    if hasattr(f, "seek") and callable(f.seek):
        f.seek(0)


def _save_image_as_webp(img, field, filename, *, source):
    """Save a PIL image as WebP to a model field safely."""
    buffer = BytesIO()
    img.save(
        buffer,
        format="WEBP",
        quality=95,  # Not too much compression in case images are used in print
        method=6,  # Max effort / smallest image, as we run async
        lossless=False,
    )
    source_name = source.name
    field.save(filename, ContentFile(buffer.getvalue()), save=False)
    instance = field.instance
    # If a new file was uploaded while we processed the old one, we do not
    # want to everride it.
    with transaction.atomic():
        current_name = (
            type(instance)
            ._base_manager.select_for_update()
            .filter(pk=instance.pk)
            .values_list(source.field.name, flat=True)
            .first()
        )
        if current_name == source_name:
            instance.save(update_fields=[field.field.name])
            return True
    field.storage.delete(field.name)
    return False


def load_img(image):
    from PIL import Image  # noqa: PLC0415 -- slow import

    try:
        img = _open_image(image)
    except Image.UnidentifiedImageError:
        return None

    if (img.mode == "P" and "transparency" in img.info) or img.mode.lower() in (
        "la",
        "pa",
    ):
        img = img.convert("RGBA")
    elif img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    return img


def process_image(*, image, generate_thumbnail=False):
    """
    This function receives an image that has been uploaded, and processes it
    by reducing its file size and stripping its metadata.
    All images are converted to WebP.
    """
    try:
        img = load_img(image)
    except Exception:  # noqa: BLE001 -- worker must not crash
        # We keep the file rather than deleting user data, but we only ever
        # serve it as image data type to be safe against e.g. XSS.
        logger.exception("Failed to process image %s, leaving it in place", image.name)
        return
    if not img:
        if not isinstance(image.field, models.ImageField):
            return
        # An image was loaded successfully but is empty / not in an allowed
        # format, so we delete it.
        instance = image.instance
        fields = [image]
        update_fields = [image.field.name]
        for size in THUMBNAIL_SIZES:
            thumbnail_field_name = get_thumbnail_field_name(image, size)
            try:
                instance._meta.get_field(thumbnail_field_name)
            except FieldDoesNotExist:
                continue
            thumbnail = getattr(instance, thumbnail_field_name)
            if thumbnail:
                fields.append(thumbnail)
                update_fields.append(thumbnail_field_name)
        try:
            for field in fields:
                field.delete(save=False)
            instance.save(update_fields=update_fields)
        except Exception:
            logger.exception("Failed to delete undecodable image %s", image.name)
        return
    from PIL import ExifTags, Image, ImageOps  # noqa: PLC0415 -- slow import

    # We downscale FIRST and then operate on the smaller image to prevent memory issues
    max_size = (settings.IMAGE_DEFAULT_MAX_WIDTH, settings.IMAGE_DEFAULT_MAX_HEIGHT)
    if img.getexif().get(ExifTags.Base.Orientation) in (5, 6, 7, 8):
        max_size = max_size[::-1]
    img.thumbnail(max_size, resample=Image.Resampling.LANCZOS)
    ImageOps.exif_transpose(img, in_place=True)

    # Overwrite the original image with the processed, converted image
    path = Path(image.path)
    save_path = path.with_suffix(".webp")

    image_field = getattr(image.instance, image.field.name)
    if not _save_image_as_webp(img, image_field, save_path.name, source=image):
        return
    if save_path != path:
        with suppress(Exception):
            path.unlink()

    if generate_thumbnail:
        for size in THUMBNAIL_SIZES:
            create_thumbnail(image, size, processed_img=img)


def get_thumbnail_field_name(image, size):
    thumbnail_field_name = f"{image.field.name}_thumbnail"
    if size != "default":
        thumbnail_field_name += f"_{size}"
    return thumbnail_field_name


def create_thumbnail(image, size, processed_img=None):
    """Create a thumbnail from an image field.

    Args:
        image: ImageFieldFile to create thumbnail from
        size: Thumbnail size key from THUMBNAIL_SIZES
        processed_img: Optional already-processed PIL Image to avoid reloading from disk
    """
    if size not in THUMBNAIL_SIZES:
        return None
    thumbnail_field_name = get_thumbnail_field_name(image, size)
    try:
        image.instance._meta.get_field(thumbnail_field_name)
    except FieldDoesNotExist:
        return None

    img = None
    if processed_img is not None:
        img = processed_img.copy()
    else:
        with suppress(Exception):
            img = load_img(image)
    if not img:
        return None

    from PIL import Image  # noqa: PLC0415 -- slow import

    img.thumbnail(THUMBNAIL_SIZES[size], resample=Image.Resampling.LANCZOS)
    thumbnail_field = getattr(image.instance, thumbnail_field_name)
    thumbnail_name = Path(image.name).stem + f"_thumbnail_{size}.webp"

    if not _save_image_as_webp(img, thumbnail_field, thumbnail_name, source=image):
        return None
    return thumbnail_field


def queue_thumbnail_regeneration(image):
    instance = getattr(image, "instance", None)
    if not instance or not getattr(instance, "pk", None):
        return
    model_name = instance._meta.model_name.capitalize()
    lock_key = f"thumbnail_regen:{model_name}:{instance.pk}:{image.field.name}"
    if not cache.add(lock_key, True, timeout=60):
        return

    task_generate_thumbnails.apply_async(
        kwargs={"field": image.field.name, "model": model_name, "pk": instance.pk}
    )


def get_image_for_model(*, model: str, pk: int, field: str):
    model_class = {
        "Answer": Answer,
        "Event": Event,
        "Profilepicture": ProfilePicture,
        "Submission": Submission,
    }.get(model)
    if model_class is None:
        return None
    with scopes_disabled():
        queryset = model_class.objects.filter(pk=pk)
        if model == "Submission":
            queryset = queryset.select_related("event")
        elif model == "Answer":
            queryset = queryset.select_related(
                "question__event", "submission", "speaker", "review"
            )
        instance = queryset.first()
    if not instance:
        return None
    return getattr(instance, field, None) or None


def get_thumbnail(image, size):
    thumbnail_field_name = get_thumbnail_field_name(image, size)
    try:
        image.instance._meta.get_field(thumbnail_field_name)
    except FieldDoesNotExist:
        return image

    thumbnail_field = getattr(image.instance, thumbnail_field_name, None)
    if thumbnail_field and thumbnail_field.storage.exists(thumbnail_field.path):
        return thumbnail_field
    queue_thumbnail_regeneration(image)
    return image
