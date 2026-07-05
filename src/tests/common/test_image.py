# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import logging
import warnings
from io import BytesIO
from pathlib import Path

import PIL.Image
import pytest
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.uploadhandler import TemporaryUploadedFile
from django.test import override_settings
from PIL import Image

from pretalx.common.image import (
    THUMBNAIL_SIZES,
    create_thumbnail,
    get_thumbnail,
    get_thumbnail_field_name,
    load_img,
    process_image,
    queue_thumbnail_regeneration,
    validate_image,
)
from tests.factories import EventFactory, ProfilePictureFactory, UserFactory

pytestmark = pytest.mark.unit


class _NonSeekableStream:
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


@pytest.mark.parametrize(
    "max_pixels", (5, 99), ids=("pil_hard_error_above_2x", "band_between_1x_and_2x")
)
def test_validate_image_rejects_decompression_bomb(make_image, monkeypatch, max_pixels):
    monkeypatch.setattr(PIL.Image, "MAX_IMAGE_PIXELS", max_pixels)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PIL.Image.DecompressionBombWarning)
        with pytest.raises(ValidationError) as exc_info:
            validate_image(make_image(width=10, height=10))  # 100 pixels
    assert "pixels" in str(exc_info.value)


def test_validate_image_with_temporary_file_path(make_image):
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
        ("CMYK", "JPEG", "RGB"),
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


def test_load_img_rejects_disallowed_format():
    buf = BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="TIFF")
    buf.seek(0)

    assert load_img(buf) is None


def test_load_img_raises_for_decompression_bomb(monkeypatch):
    monkeypatch.setattr(PIL.Image, "MAX_IMAGE_PIXELS", 99)
    buf = BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="PNG")  # 100 > 99
    buf.seek(0)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PIL.Image.DecompressionBombWarning)
        with pytest.raises(PIL.Image.DecompressionBombError):
            load_img(buf)


@pytest.mark.parametrize("size", list(THUMBNAIL_SIZES.keys()))
@pytest.mark.django_db
def test_get_thumbnail_field_name(make_image, size):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())

    expected = "avatar_thumbnail" if size == "default" else f"avatar_thumbnail_{size}"
    assert get_thumbnail_field_name(pic.avatar, size) == expected


@pytest.mark.django_db
def test_process_image_converts_to_webp(make_image):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    original_path = Path(pic.avatar.path)

    process_image(image=pic.avatar)

    pic.refresh_from_db()
    assert pic.avatar.path.endswith(".webp")
    assert not original_path.exists()


@pytest.mark.django_db
def test_process_image_with_thumbnails(make_image):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())

    process_image(image=pic.avatar, generate_thumbnail=True)

    pic.refresh_from_db()
    assert pic.avatar.path.endswith(".webp")
    assert pic.avatar_thumbnail.path.endswith(".webp")
    assert pic.avatar_thumbnail_tiny.path.endswith(".webp")


@pytest.mark.django_db
def test_process_image_deletes_invalid_image_and_thumbnails():
    user = UserFactory()
    pic = ProfilePictureFactory(
        user=user, avatar=SimpleUploadedFile("bad.html", b"<script>alert(1)</script>")
    )
    pic.avatar_thumbnail = SimpleUploadedFile("bad_thumbnail.webp", b"thumbnail")
    pic.avatar_thumbnail_tiny = SimpleUploadedFile("bad_thumbnail_tiny.webp", b"tiny")
    pic.save()
    paths = [
        Path(pic.avatar.path),
        Path(pic.avatar_thumbnail.path),
        Path(pic.avatar_thumbnail_tiny.path),
    ]
    assert all(path.exists() for path in paths)

    result = process_image(image=pic.avatar)

    assert result is None
    assert not any(path.exists() for path in paths)
    pic.refresh_from_db()
    assert not pic.avatar
    assert not pic.avatar_thumbnail
    assert not pic.avatar_thumbnail_tiny


@pytest.mark.django_db
def test_process_image_delete_keeps_unmanaged_fields():
    user = UserFactory()
    pic = ProfilePictureFactory(
        user=user, avatar=SimpleUploadedFile("bad.html", b"<script>alert(1)</script>")
    )
    stored_path = Path(pic.avatar.path)
    assert stored_path.exists()
    # No thumbnails exist on this instance, so the cleanup touches only `avatar`.
    assert not pic.avatar_thumbnail

    type(pic).objects.filter(pk=pic.pk).update(
        avatar_thumbnail="avatars/concurrent.webp"
    )

    result = process_image(image=pic.avatar)

    assert result is None
    assert not stored_path.exists()
    pic.refresh_from_db()
    assert not pic.avatar
    assert pic.avatar_thumbnail == "avatars/concurrent.webp"


@pytest.mark.django_db
def test_process_image_deletes_invalid_image_without_thumbnail_field():
    event = EventFactory(
        logo=SimpleUploadedFile("bad.html", b"<script>alert(1)</script>")
    )
    stored_path = Path(event.logo.path)
    assert stored_path.exists()

    result = process_image(image=event.logo)

    assert result is None
    assert not stored_path.exists()
    event.refresh_from_db()
    assert not event.logo


@pytest.mark.django_db
def test_process_image_delete_logs_on_cleanup_failure(monkeypatch, caplog):
    user = UserFactory()
    pic = ProfilePictureFactory(
        user=user, avatar=SimpleUploadedFile("bad.html", b"<script>alert(1)</script>")
    )

    def boom(*args, **kwargs):
        raise OSError("storage unavailable")

    monkeypatch.setattr(type(pic), "save", boom)
    caplog.set_level(logging.ERROR)

    result = process_image(image=pic.avatar)

    assert result is None
    assert "Failed to delete undecodable image" in caplog.text


@pytest.mark.django_db
def test_process_image_keeps_oversized_image(make_image, monkeypatch, caplog):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image(width=10, height=10))
    stored_path = Path(pic.avatar.path)
    monkeypatch.setattr(PIL.Image, "MAX_IMAGE_PIXELS", 99)
    caplog.set_level(logging.ERROR)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PIL.Image.DecompressionBombWarning)
        result = process_image(image=pic.avatar)

    assert result is None
    assert stored_path.exists()
    pic.refresh_from_db()
    assert pic.avatar
    assert "Failed to process image" in caplog.text


@pytest.mark.django_db
def test_process_image_keeps_corrupt_image(caplog):
    buf = BytesIO()
    Image.new("L", (100, 100)).save(buf, format="PNG")
    truncated = buf.getvalue()[:60]
    user = UserFactory()
    pic = ProfilePictureFactory(
        user=user, avatar=SimpleUploadedFile("truncated.png", truncated)
    )
    stored_path = Path(pic.avatar.path)
    caplog.set_level(logging.ERROR)

    result = process_image(image=pic.avatar)

    assert result is None
    assert stored_path.exists()
    pic.refresh_from_db()
    assert pic.avatar
    assert "Failed to process image" in caplog.text


@pytest.mark.django_db
def test_create_thumbnail_invalid_size(make_image):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())

    result = create_thumbnail(pic.avatar, "nonexistent_size")

    assert result is None


@pytest.mark.parametrize("size", list(THUMBNAIL_SIZES.keys()))
@pytest.mark.django_db
def test_create_thumbnail_from_disk(make_image, size):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())

    result = create_thumbnail(pic.avatar, size)

    assert result is not None
    assert result.path.endswith(".webp")


@pytest.mark.parametrize("size", list(THUMBNAIL_SIZES.keys()))
@pytest.mark.django_db
def test_create_thumbnail_with_processed_img(make_image, size):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    processed = Image.new("RGB", (100, 100), color="green")

    result = create_thumbnail(pic.avatar, size, processed_img=processed)

    assert result is not None
    assert result.path.endswith(".webp")


@pytest.mark.django_db
def test_get_thumbnail_falls_back_to_source_and_queues_regeneration(
    make_image, monkeypatch
):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    calls = []
    monkeypatch.setattr(
        "pretalx.common.image.queue_thumbnail_regeneration", calls.append
    )

    result = get_thumbnail(pic.avatar, "default")

    assert result == pic.avatar
    assert calls == [pic.avatar]


@pytest.mark.django_db
def test_get_thumbnail_returns_existing(make_image):
    user = UserFactory()
    pic = ProfilePictureFactory(
        user=user, avatar=make_image(), avatar_thumbnail=make_image("thumb.png")
    )

    result = get_thumbnail(pic.avatar, "default")

    assert result == pic.avatar_thumbnail


@pytest.mark.django_db
def test_create_thumbnail_returns_none_for_missing_field(make_image):
    event = EventFactory(logo=make_image("logo.png"))

    result = create_thumbnail(event.logo, "default")

    assert result is None


@pytest.mark.django_db
def test_get_thumbnail_returns_image_for_missing_field(make_image):
    event = EventFactory(logo=make_image("logo.png"))

    result = get_thumbnail(event.logo, "default")

    assert result == event.logo


def test_validate_image_non_seekable_readable(make_image):
    data = make_image().read()

    validate_image(_NonSeekableStream(data))


@pytest.mark.django_db
def test_process_image_webp_input_skips_unlink(make_image):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image("test.webp"))

    process_image(image=pic.avatar)

    pic.refresh_from_db()
    assert pic.avatar.path.endswith(".webp")


@pytest.mark.django_db
def test_queue_thumbnail_regeneration_dispatches_task(make_image, monkeypatch):
    cache.clear()
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    captured = {}

    def fake_apply_async(*, kwargs, **_):
        captured.update(kwargs)

    monkeypatch.setattr(
        "pretalx.common.tasks.task_generate_thumbnails.apply_async", fake_apply_async
    )

    queue_thumbnail_regeneration(pic.avatar)

    assert captured == {"field": "avatar", "model": "Profilepicture", "pk": pic.pk}


@pytest.mark.django_db
@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
def test_queue_thumbnail_regeneration_deduplicates_in_flight(make_image, monkeypatch):
    cache.clear()
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    calls = []
    monkeypatch.setattr(
        "pretalx.common.tasks.task_generate_thumbnails.apply_async",
        lambda **kw: calls.append(kw),
    )

    queue_thumbnail_regeneration(pic.avatar)
    queue_thumbnail_regeneration(pic.avatar)

    assert len(calls) == 1


@pytest.mark.django_db
def test_queue_thumbnail_regeneration_skips_unsaved_instance(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "pretalx.common.tasks.task_generate_thumbnails.apply_async",
        lambda **kw: calls.append(kw),
    )

    class _Fake:
        instance = type("X", (), {"pk": None})()
        field = type("F", (), {"name": "avatar"})()

    queue_thumbnail_regeneration(_Fake())

    assert calls == []


@pytest.mark.django_db
def test_create_thumbnail_returns_none_for_invalid_image_on_disk():
    user = UserFactory()
    pic = ProfilePictureFactory(
        user=user, avatar=SimpleUploadedFile("bad.png", b"not-an-image")
    )

    result = create_thumbnail(pic.avatar, "default")

    assert result is None
