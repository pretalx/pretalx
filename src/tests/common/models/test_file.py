import uuid
from pathlib import Path

import pytest
from django.core.files.base import ContentFile
from django_scopes import scopes_disabled

from pretalx.common.models.file import CachedFile, cachedfile_name
from tests.factories import CachedFileFactory

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
def test_cachedfile_post_delete_deletes_physical_file(tmp_path, settings):
    """When a CachedFile is deleted, the post_delete signal removes the
    physical file from storage."""
    settings.MEDIA_ROOT = str(tmp_path)
    cached_file = CachedFileFactory()
    cached_file.file.save("test.txt", ContentFile(b"hello"), save=True)
    file_path = Path(cached_file.file.path)
    assert file_path.exists()

    cached_file.delete()

    assert not file_path.exists()


@pytest.mark.django_db
def test_cachedfile_post_delete_without_file():
    """Deleting a CachedFile without a file attached does not raise."""
    cached_file = CachedFileFactory(file=None)

    cached_file.delete()

    with scopes_disabled():
        assert not CachedFile.objects.filter(pk=cached_file.pk).exists()
