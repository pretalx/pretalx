# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from pathlib import Path

import pytest
from django.core.files.storage import default_storage
from django_scopes import scope

from pretalx.common.tasks import (
    task_cleanup_file,
    task_generate_thumbnails,
    task_process_image,
)
from tests.factories import ProfilePictureFactory, SubmissionFactory, UserFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("task", "kwargs"),
    (
        (task_process_image, {"generate_thumbnail": False}),
        (task_generate_thumbnails, {}),
        (task_cleanup_file, {"path": "/nonexistent/file.png"}),
    ),
    ids=("process_image", "generate_thumbnails", "cleanup_file"),
)
def test_tasks_ignore_missing_targets(task, kwargs):
    pic = ProfilePictureFactory(user=UserFactory())

    task(model="UnknownModel", pk=1, field="avatar", **kwargs)
    task(model="Profilepicture", pk=999999, field="avatar", **kwargs)
    task(model="Profilepicture", pk=pic.pk, field="avatar", **kwargs)

    pic.refresh_from_db()
    assert not pic.avatar


@pytest.mark.django_db
def test_task_process_image_converts_to_webp_and_generates_thumbnails(make_image):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    original_path = Path(pic.avatar.path)

    task_process_image(
        model="Profilepicture", pk=pic.pk, field="avatar", generate_thumbnail=True
    )

    pic.refresh_from_db()
    assert pic.avatar.path.endswith(".webp")
    assert not original_path.exists()
    assert pic.avatar_thumbnail.path.endswith(".webp")
    assert pic.avatar_thumbnail_tiny.path.endswith(".webp")


@pytest.mark.django_db
def test_task_process_image_runs_without_active_scope(make_image):
    submission = SubmissionFactory(image=make_image())

    with scope():
        task_process_image(
            model="Submission",
            pk=submission.pk,
            field="image",
            generate_thumbnail=False,
        )

    submission.refresh_from_db()
    assert submission.image.path.endswith(".webp")


@pytest.mark.django_db
def test_image_tasks_catch_processing_errors(make_image):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    task_process_image(
        model="Profilepicture", pk=pic.pk, field="avatar", generate_thumbnail=True
    )
    pic.refresh_from_db()
    Path(pic.avatar_thumbnail.path).unlink()
    Path(pic.avatar_thumbnail_tiny.path).unlink()
    avatar_path = Path(pic.avatar.path)

    avatar_dir = avatar_path.parent
    original_mode = avatar_dir.stat().st_mode
    try:
        avatar_dir.chmod(0o555)
        task_process_image(
            model="Profilepicture", pk=pic.pk, field="avatar", generate_thumbnail=False
        )
        task_generate_thumbnails(model="Profilepicture", pk=pic.pk, field="avatar")
    finally:
        avatar_dir.chmod(original_mode)

    pic.refresh_from_db()
    assert Path(pic.avatar.path) == avatar_path
    assert not Path(pic.avatar_thumbnail.path).exists()


@pytest.mark.django_db
def test_task_cleanup_file_deletes_only_orphaned_files(make_image):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user, avatar=make_image())
    current_path = pic.avatar.path
    orphan_name = default_storage.save("avatars/orphan.png", make_image())
    orphan_path = default_storage.path(orphan_name)
    assert Path(orphan_path).exists()

    task_cleanup_file(
        model="Profilepicture", pk=pic.pk, field="avatar", path=current_path
    )
    task_cleanup_file(
        model="Profilepicture", pk=pic.pk, field="avatar", path=orphan_path
    )

    assert not Path(orphan_path).exists()
    assert Path(current_path).exists()


@pytest.mark.django_db
def test_task_cleanup_file_with_empty_field_deletes_file_once_writable(make_image):
    user = UserFactory()
    pic = ProfilePictureFactory(user=user)
    stored_name = default_storage.save("orphaned_test_file.png", make_image())
    stored_path = default_storage.path(stored_name)
    parent_dir = Path(stored_path).parent
    original_mode = parent_dir.stat().st_mode

    try:
        parent_dir.chmod(0o555)
        task_cleanup_file(
            model="Profilepicture", pk=pic.pk, field="avatar", path=stored_path
        )
        assert Path(stored_path).exists()
    finally:
        parent_dir.chmod(original_mode)

    task_cleanup_file(
        model="Profilepicture", pk=pic.pk, field="avatar", path=stored_path
    )

    assert not Path(stored_path).exists()
