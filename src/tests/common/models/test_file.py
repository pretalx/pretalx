# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import uuid
from pathlib import Path

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory

from pretalx.common.models.file import CachedFile, cachedfile_name
from tests.factories import CachedFileFactory

rf = RequestFactory()

pytestmark = pytest.mark.unit


def test_cachedfile_name_uses_id_and_extension():
    instance = CachedFile(id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    result = cachedfile_name(instance, "report.pdf")

    assert result.startswith("cachedfiles/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.")
    assert result.endswith(".pdf")
    # Middle part is a 12-char random secret
    parts = result.split(".")
    assert len(parts[1]) == 12


def test_cachedfile_name_handles_dotless_filename():
    instance = CachedFile(id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    result = cachedfile_name(instance, "noextension")

    assert result.endswith(".noextension")


def test_cachedfile_str():
    file_id = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    cached_file = CachedFile(id=file_id, file="cachedfiles/test.zip")

    result = str(cached_file)

    assert (
        result
        == "CachedFile(id=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee, file=cachedfiles/test.zip)"
    )


@pytest.mark.django_db
def test_cachedfile_delete_removes_physical_file(
    tmp_path, settings, django_capture_on_commit_callbacks
):
    """Deleting a CachedFile schedules removal of the physical file via
    FileCleanupMixin."""
    settings.MEDIA_ROOT = str(tmp_path)
    cached_file = CachedFileFactory()
    cached_file.file.save("test.txt", ContentFile(b"hello"), save=True)
    file_path = Path(cached_file.file.path)
    assert file_path.exists()

    with django_capture_on_commit_callbacks(execute=True):
        cached_file.delete()

    assert not file_path.exists()


@pytest.mark.django_db
def test_cachedfile_delete_without_file():
    """Deleting a CachedFile without a file attached does not raise."""
    cached_file = CachedFileFactory(file=None)

    cached_file.delete()

    assert not CachedFile.objects.filter(pk=cached_file.pk).exists()


def test_build_absolute_url_returns_none_for_falsy_file():
    request = rf.get("/")

    assert CachedFile.build_absolute_url(None, request) is None
    assert CachedFile.build_absolute_url("", request) is None


def test_build_absolute_url_returns_none_without_url():
    request = rf.get("/")

    assert CachedFile.build_absolute_url(object(), request) is None


@pytest.mark.django_db
def test_build_absolute_url_returns_none_without_request():
    uploaded = SimpleUploadedFile("test.txt", b"content")
    cached_file = CachedFileFactory(file=uploaded)

    assert CachedFile.build_absolute_url(cached_file.file, None) is None


@pytest.mark.django_db
def test_build_absolute_url_returns_absolute_uri():
    uploaded = SimpleUploadedFile("test.txt", b"content")
    cached_file = CachedFileFactory(file=uploaded)
    request = rf.get("/api/test/")

    result = CachedFile.build_absolute_url(cached_file.file, request)

    assert result == f"http://testserver{cached_file.file.url}"
