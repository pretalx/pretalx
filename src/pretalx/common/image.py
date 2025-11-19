# SPDX-FileCopyrightText: 2024-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from contextlib import suppress
from functools import partial
from io import BytesIO
from pathlib import Path

from csp.decorators import csp_update
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.translation import gettext_lazy as _

THUMBNAIL_SIZES = {
    "tiny": (64, 64),
    "default": (460, 460),
}
MAX_DIMENSIONS = (
    settings.IMAGE_DEFAULT_MAX_WIDTH,
    settings.IMAGE_DEFAULT_MAX_HEIGHT,
)
WEBP_SETTINGS = {
    "format": "WEBP",
    "quality": 95,  # Not too much compression in case images are used in print
    "method": 6,  # Max effort / smallest image, as we run async
    "lossless": False,
}

gravatar_csp = partial(
    csp_update,
    {
        "img-src": "https://www.gravatar.com",
        "connect-src": ("'self'", "https://www.gravatar.com"),
    },
)


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

    from PIL import Image

    try:
        try:
            image = Image.open(file)
            # verify() must be called immediately after the constructor.
            image.verify()
        except Image.DecompressionBombError:
            raise ValidationError(
                _(
                    "The file you uploaded has a very large number of pixels, please upload a picture with smaller dimensions."
                )
            )

        # load() is a potential DoS vector (see Django bug #18520), so we verify the size first
        if image.width * image.height > Image.MAX_IMAGE_PIXELS:
            raise ValidationError(
                _(
                    "The file you uploaded has a very large number of pixels, please upload a picture with smaller dimensions."
                )
            )
    except Exception as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError(
            _(
                "Upload a valid image. The file you uploaded was either not an image or a corrupted image."
            )
        ) from exc
    if hasattr(f, "seek") and callable(f.seek):
        f.seek(0)


def _save_image_as_webp(img, field, filename):
    """Helper to save a PIL Image as WebP to a model image field and save the instance."""
    buffer = BytesIO()
    img.save(buffer, **WEBP_SETTINGS)
    field.save(filename, ContentFile(buffer.getvalue()))
    field.instance.save()


def load_img(image):
    from PIL import Image

    try:
        img = Image.open(image)
    except Exception:
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
    All images are converted to WebP format for optimal size and quality.
    Image must be an ImageFieldFile, e.g. user.avatar.
    """
    img = load_img(image)
    if not img:
        return
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(img)
    img_without_exif = Image.new(img.mode, img.size)
    img_without_exif.putdata(img.getdata())
    img_without_exif.thumbnail(MAX_DIMENSIONS, resample=Image.Resampling.LANCZOS)

    # Overwrite the original image with the processed, converted image
    path = Path(image.path)
    save_path = path.with_suffix(".webp")

    image_field = getattr(image.instance, image.field.name)
    _save_image_as_webp(img_without_exif, image_field, save_path.name)
    if save_path != path:
        with suppress(Exception):
            path.unlink()

    if generate_thumbnail:
        for size in THUMBNAIL_SIZES:
            create_thumbnail(image, size, processed_img=img_without_exif)


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
        return
    thumbnail_field_name = get_thumbnail_field_name(image, size)
    if not image.instance._meta.get_field(thumbnail_field_name):
        return

    img = None
    if processed_img is not None:
        img = processed_img.copy()
    else:
        with suppress(Exception):
            img = load_img(image)
    if not img:
        return

    from PIL import Image

    img.thumbnail(THUMBNAIL_SIZES[size], resample=Image.Resampling.LANCZOS)
    thumbnail_field = getattr(image.instance, thumbnail_field_name)
    thumbnail_name = Path(image.name).stem + f"_thumbnail_{size}.webp"

    _save_image_as_webp(img, thumbnail_field, thumbnail_name)
    return thumbnail_field


def get_thumbnail(image, size):
    thumbnail_field_name = get_thumbnail_field_name(image, size)
    if not (image.instance._meta.get_field(thumbnail_field_name)):
        return image

    thumbnail_field = getattr(image.instance, thumbnail_field_name, None)
    if not thumbnail_field or not thumbnail_field.storage.exists(thumbnail_field.path):
        return create_thumbnail(image, size)
    return thumbnail_field
