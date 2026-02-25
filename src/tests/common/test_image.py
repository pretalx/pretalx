import warnings
from io import BytesIO
from pathlib import Path

import PIL.Image
import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.uploadhandler import TemporaryUploadedFile
from PIL import Image

from pretalx.common.image import (
    THUMBNAIL_SIZES,
    create_thumbnail,
    get_thumbnail,
    get_thumbnail_field_name,
    load_img,
    process_image,
    validate_image,
)
from pretalx.person.models.picture import ProfilePicture
from tests.factories import EventFactory, UserFactory

pytestmark = pytest.mark.unit


class _NonSeekableStream:
    """Minimal read-only stream without seek(), representing non-seekable
    inputs like HTTP response bodies or pipe reads."""

    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data


def test_validate_image_none():
    validate_image(None)


def test_validate_image_valid_uploaded_file(make_image):
    validate_image(make_image())


def test_validate_image_dict_content(make_image):
    validate_image({"content": make_image().read()})


def test_validate_image_rewinds_seekable_file(make_image):
    f = make_image()
    f.seek(5)

    validate_image(f)

    assert f.tell() == 0


@pytest.mark.parametrize(
    "data",
    (b"not an image at all", b"\x89PNG\r\n\x1a\n" + b"\x00" * 100),
    ids=("random_bytes", "corrupt_png_header"),
)
def test_validate_image_rejects_invalid_data(data):
    with pytest.raises(ValidationError):
        validate_image(BytesIO(data))


def test_validate_image_decompression_bomb(make_image, monkeypatch):
    """A decompression bomb should raise a ValidationError, not crash."""
    monkeypatch.setattr(PIL.Image, "MAX_IMAGE_PIXELS", 5)

    with pytest.raises(ValidationError):
        validate_image(make_image(width=10, height=10))


def test_validate_image_exceeds_max_pixels(make_image, monkeypatch):
    """An image exceeding MAX_IMAGE_PIXELS but below PIL's 2x bomb
    threshold should be caught by the manual pixel-count check."""
    monkeypatch.setattr(PIL.Image, "MAX_IMAGE_PIXELS", 99)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PIL.Image.DecompressionBombWarning)
        with pytest.raises(ValidationError):
            validate_image(make_image(width=10, height=10))  # 100 > 99


def test_validate_image_with_temporary_file_path(make_image):
    """When a file has a temporary_file_path attribute, it is used directly."""
    upload = TemporaryUploadedFile(
        name="test.png", content_type="image/png", size=0, charset=None
    )
    upload.write(make_image().read())
    upload.file.flush()

    validate_image(upload)


@pytest.mark.parametrize(
    ("mode", "fmt", "expected_mode"),
    (
        ("RGB", "PNG", "RGB"),
        ("RGBA", "PNG", "RGBA"),
        ("L", "PNG", "RGB"),
        ("CMYK", "TIFF", "RGB"),
        ("LA", "PNG", "RGBA"),
    ),
)
def test_load_img_converts_mode(mode, fmt, expected_mode):
    buf = BytesIO()
    img = Image.new(mode, (10, 10))
    img.save(buf, format=fmt)
    buf.seek(0)

    result = load_img(buf)

    assert result is not None
    assert result.mode == expected_mode


def test_load_img_converts_palette_with_transparency():
    """P mode with transparency should become RGBA."""
    buf = BytesIO()
    img = Image.new("P", (10, 10))
    img.info["transparency"] = 0
    img.save(buf, format="PNG", transparency=0)
    buf.seek(0)

    result = load_img(buf)

    assert result is not None
    assert result.mode == "RGBA"


@pytest.mark.parametrize(
    "data",
    (b"not an image", b"\x89PNG\r\n\x1a\n" + b"\xff" * 50),
    ids=("random_bytes", "corrupt_png"),
)
def test_load_img_returns_none_for_invalid_data(data):
    assert load_img(BytesIO(data)) is None


@pytest.mark.parametrize("size", list(THUMBNAIL_SIZES.keys()))
@pytest.mark.django_db
def test_get_thumbnail_field_name(make_image, size):
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())

    expected = "avatar_thumbnail" if size == "default" else f"avatar_thumbnail_{size}"
    assert get_thumbnail_field_name(pic.avatar, size) == expected


@pytest.mark.django_db
def test_process_image_converts_to_webp(make_image):
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())
    original_path = Path(pic.avatar.path)

    process_image(image=pic.avatar)

    pic.refresh_from_db()
    assert pic.avatar.path.endswith(".webp")
    assert not original_path.exists()


@pytest.mark.django_db
def test_process_image_with_thumbnails(make_image):
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())

    process_image(image=pic.avatar, generate_thumbnail=True)

    pic.refresh_from_db()
    assert pic.avatar.path.endswith(".webp")
    assert pic.avatar_thumbnail.path.endswith(".webp")
    assert pic.avatar_thumbnail_tiny.path.endswith(".webp")


@pytest.mark.django_db
def test_process_image_returns_none_for_invalid_image():
    user = UserFactory()
    pic = ProfilePicture.objects.create(
        user=user, avatar=SimpleUploadedFile("bad.png", b"not-an-image")
    )

    result = process_image(image=pic.avatar)

    assert result is None


@pytest.mark.django_db
def test_create_thumbnail_invalid_size(make_image):
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())

    result = create_thumbnail(pic.avatar, "nonexistent_size")

    assert result is None


@pytest.mark.parametrize("size", list(THUMBNAIL_SIZES.keys()))
@pytest.mark.django_db
def test_create_thumbnail_from_disk(make_image, size):
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())

    result = create_thumbnail(pic.avatar, size)

    assert result is not None
    assert result.path.endswith(".webp")


@pytest.mark.parametrize("size", list(THUMBNAIL_SIZES.keys()))
@pytest.mark.django_db
def test_create_thumbnail_with_processed_img(make_image, size):
    """Passing a processed_img avoids reloading from disk."""
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())
    processed = Image.new("RGB", (100, 100), color="green")

    result = create_thumbnail(pic.avatar, size, processed_img=processed)

    assert result is not None
    assert result.path.endswith(".webp")


@pytest.mark.django_db
def test_get_thumbnail_creates_missing(make_image):
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())

    result = get_thumbnail(pic.avatar, "default")

    assert result is not None
    assert result.path.endswith(".webp")


@pytest.mark.django_db
def test_get_thumbnail_returns_existing(make_image):
    user = UserFactory()
    pic = ProfilePicture.objects.create(
        user=user, avatar=make_image(), avatar_thumbnail=make_image("thumb.png")
    )

    result = get_thumbnail(pic.avatar, "default")

    assert result == pic.avatar_thumbnail


@pytest.mark.django_db
def test_create_thumbnail_returns_none_for_missing_field(make_image):
    """Event.logo has no logo_thumbnail field, so create_thumbnail should
    return None instead of raising FieldDoesNotExist."""
    event = EventFactory(logo=make_image("logo.png"))

    result = create_thumbnail(event.logo, "default")

    assert result is None


@pytest.mark.django_db
def test_get_thumbnail_returns_image_for_missing_field(make_image):
    """Event.logo has no logo_thumbnail field, so get_thumbnail should
    fall back to returning the original image."""
    event = EventFactory(logo=make_image("logo.png"))

    result = get_thumbnail(event.logo, "default")

    assert result == event.logo


def test_validate_image_non_seekable_readable(make_image):
    """A readable stream without seek() still validates correctly."""
    data = make_image().read()

    validate_image(_NonSeekableStream(data))


@pytest.mark.django_db
def test_process_image_webp_input_skips_unlink(make_image):
    """When the original file already has a .webp extension, process_image
    should not attempt to unlink it (save_path == path)."""
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image("test.webp"))

    process_image(image=pic.avatar)

    pic.refresh_from_db()
    assert pic.avatar.path.endswith(".webp")


@pytest.mark.django_db
def test_create_thumbnail_returns_none_for_invalid_image_on_disk():
    """When the image file is invalid and no processed_img is provided,
    create_thumbnail returns None (the thumbnail field exists but the
    image cannot be loaded)."""
    user = UserFactory()
    pic = ProfilePicture.objects.create(
        user=user, avatar=SimpleUploadedFile("bad.png", b"not-an-image")
    )

    result = create_thumbnail(pic.avatar, "default")

    assert result is None
