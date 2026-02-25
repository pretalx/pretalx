from pathlib import Path

import pytest
from django.core.files.storage import default_storage

from pretalx.common.tasks import task_cleanup_file, task_process_image
from pretalx.person.models.picture import ProfilePicture
from tests.factories import UserFactory

pytestmark = pytest.mark.unit


def test_task_process_image_unknown_model():
    """Unknown model name returns early without any DB query."""
    task_process_image(
        model="UnknownModel", pk=1, field="avatar", generate_thumbnail=False
    )


@pytest.mark.django_db
def test_task_process_image_instance_not_found():
    task_process_image(
        model="Profilepicture", pk=999999, field="avatar", generate_thumbnail=False
    )


@pytest.mark.django_db
def test_task_process_image_field_not_set():
    """When the image field on the instance is empty, returns early."""
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user)

    task_process_image(
        model="Profilepicture", pk=pic.pk, field="avatar", generate_thumbnail=False
    )

    pic.refresh_from_db()
    assert not pic.avatar


@pytest.mark.django_db
def test_task_process_image_converts_to_webp(make_image):
    """Task resolves the model, fetches the instance, and converts the image."""
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())
    original_path = Path(pic.avatar.path)

    task_process_image(
        model="Profilepicture", pk=pic.pk, field="avatar", generate_thumbnail=False
    )

    pic.refresh_from_db()
    assert pic.avatar.path.endswith(".webp")
    assert not original_path.exists()


@pytest.mark.django_db
def test_task_process_image_generates_thumbnails(make_image):
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())

    task_process_image(
        model="Profilepicture", pk=pic.pk, field="avatar", generate_thumbnail=True
    )

    pic.refresh_from_db()
    assert pic.avatar.path.endswith(".webp")
    assert pic.avatar_thumbnail.path.endswith(".webp")
    assert pic.avatar_thumbnail_tiny.path.endswith(".webp")


@pytest.mark.django_db
def test_task_process_image_catches_processing_error(make_image):
    """When process_image raises OSError (e.g. storage failure), the task
    catches it and logs the error instead of crashing."""
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())

    # Make the avatar directory read-only so the save operation fails with OSError
    avatar_dir = Path(pic.avatar.path).parent
    original_mode = avatar_dir.stat().st_mode
    try:
        avatar_dir.chmod(0o555)
        task_process_image(
            model="Profilepicture", pk=pic.pk, field="avatar", generate_thumbnail=False
        )
        # Task should complete without raising
    finally:
        avatar_dir.chmod(original_mode)


def test_task_cleanup_file_unknown_model():
    task_cleanup_file(
        model="UnknownModel", pk=1, field="avatar", path="/nonexistent/path"
    )


@pytest.mark.django_db
def test_task_cleanup_file_instance_not_found():
    task_cleanup_file(
        model="Profilepicture", pk=999999, field="avatar", path="/some/path"
    )


@pytest.mark.django_db
def test_task_cleanup_file_file_still_in_use(make_image):
    """When the file field still has the same path, the file is considered
    still in use and is NOT deleted."""
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())
    file_path = pic.avatar.path

    task_cleanup_file(model="Profilepicture", pk=pic.pk, field="avatar", path=file_path)

    assert Path(file_path).exists()


@pytest.mark.django_db
def test_task_cleanup_file_deletes_orphaned_file(make_image):
    """When the file field has a different path (image was updated),
    the old file is deleted."""
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user, avatar=make_image())
    current_path = pic.avatar.path

    # Create a separate orphaned file that the task should delete
    orphan_name = default_storage.save("avatars/orphan.png", make_image())
    orphan_path = default_storage.path(orphan_name)
    assert Path(orphan_path).exists()

    task_cleanup_file(
        model="Profilepicture", pk=pic.pk, field="avatar", path=orphan_path
    )

    assert not Path(orphan_path).exists()
    assert Path(current_path).exists()


@pytest.mark.django_db
def test_task_cleanup_file_path_does_not_exist():
    """When the file path doesn't exist on disk, no deletion attempt is made."""
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user)

    task_cleanup_file(
        model="Profilepicture", pk=pic.pk, field="avatar", path="/nonexistent/file.png"
    )


@pytest.mark.django_db
def test_task_cleanup_file_field_is_empty(make_image):
    """When the file field is empty (falsy) but the orphaned path exists,
    the file is deleted."""
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user)

    # Create a file via default_storage so the cleanup task can find and delete it
    stored_name = default_storage.save("orphaned_test_file.png", make_image())
    stored_path = default_storage.path(stored_name)
    assert Path(stored_path).exists()

    task_cleanup_file(
        model="Profilepicture", pk=pic.pk, field="avatar", path=stored_path
    )

    assert not Path(stored_path).exists()


@pytest.mark.django_db
def test_task_cleanup_file_oserror_during_deletion(make_image):
    """When default_storage.delete raises OSError, the task logs the error
    without crashing."""
    user = UserFactory()
    pic = ProfilePicture.objects.create(user=user)

    # Create a real file, then make its parent directory read-only so
    # deletion fails with PermissionError (an OSError subclass)
    stored_name = default_storage.save("oserror_test_file.png", make_image())
    stored_path = default_storage.path(stored_name)
    parent_dir = Path(stored_path).parent
    original_mode = parent_dir.stat().st_mode
    try:
        parent_dir.chmod(0o555)
        task_cleanup_file(
            model="Profilepicture", pk=pic.pk, field="avatar", path=stored_path
        )
        # Task should complete without raising
    finally:
        parent_dir.chmod(original_mode)
        default_storage.delete(stored_name)
