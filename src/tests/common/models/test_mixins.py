import uuid
from pathlib import Path

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.db import IntegrityError
from django_scopes import scopes_disabled

from pretalx.common.models import ActivityLog
from pretalx.common.models.mixins import SENSITIVE_KEYS
from pretalx.person.models.picture import ProfilePicture
from pretalx.submission.models import Submission
from pretalx.submission.models.question import Question
from tests.factories import (
    EventFactory,
    QuestionFactory,
    RoomFactory,
    SubmissionFactory,
    TrackFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_log_action_creates_activity_log():
    with scopes_disabled():
        submission = SubmissionFactory()
        user = UserFactory()

    log = submission.log_action("pretalx.submission.create", person=user)

    assert log is not None
    assert log.action_type == "pretalx.submission.create"
    assert log.person == user
    assert log.event == submission.event
    assert log.content_object == submission


@pytest.mark.django_db
def test_log_action_with_dot_prefix_uses_log_prefix():
    with scopes_disabled():
        submission = SubmissionFactory()

    log = submission.log_action(".update")

    assert log.action_type == f"{submission.log_prefix}.update"


@pytest.mark.django_db
def test_log_action_with_dot_prefix_without_log_prefix_returns_none():
    """If the model has no log_prefix and action starts with '.', log_action
    returns None."""
    with scopes_disabled():
        submission = SubmissionFactory()
    original_prefix = submission.log_prefix
    submission.log_prefix = None

    result = submission.log_action(".update")

    submission.log_prefix = original_prefix
    assert result is None


@pytest.mark.django_db
def test_log_action_without_pk_returns_none():
    """If the model has no pk yet (unsaved), log_action returns None."""
    submission = Submission(title="Unsaved")

    result = submission.log_action("pretalx.submission.create")

    assert result is None


@pytest.mark.django_db
def test_log_action_with_data_dict():
    with scopes_disabled():
        submission = SubmissionFactory()

    log = submission.log_action(
        "pretalx.submission.update", data={"title": "New Title"}
    )

    assert log.data == {"title": "New Title"}


@pytest.mark.django_db
def test_log_action_with_non_dict_data_raises():
    with scopes_disabled():
        submission = SubmissionFactory()

    with pytest.raises(TypeError, match="dictionary"):
        submission.log_action("pretalx.submission.update", data="not a dict")


@pytest.mark.django_db
def test_log_action_redacts_sensitive_keys():
    with scopes_disabled():
        submission = SubmissionFactory()

    log = submission.log_action(
        "pretalx.submission.update",
        data={"password": "s3cret", "api_key": "abc123", "title": "ok"},
    )

    assert log.data["password"] == "********"
    assert log.data["api_key"] == "********"
    assert log.data["title"] == "ok"


@pytest.mark.django_db
def test_log_action_does_not_redact_falsy_sensitive_values():
    with scopes_disabled():
        submission = SubmissionFactory()

    log = submission.log_action(
        "pretalx.submission.update", data={"password": "", "title": "ok"}
    )

    assert log.data["password"] == ""


@pytest.mark.django_db
def test_log_action_with_orga_flag():
    with scopes_disabled():
        submission = SubmissionFactory()

    log = submission.log_action("pretalx.submission.update", orga=True)

    assert log.is_orga_action is True


@pytest.mark.django_db
def test_log_action_with_custom_content_object():
    with scopes_disabled():
        submission = SubmissionFactory()
        event = submission.event

    log = submission.log_action("pretalx.event.update", content_object=event)

    assert log.content_object == event


@pytest.mark.django_db
def test_log_action_with_old_and_new_data():
    with scopes_disabled():
        submission = SubmissionFactory()

    log = submission.log_action(
        "pretalx.submission.update",
        old_data={"title": "Old"},
        new_data={"title": "New"},
    )

    assert log.data["changes"]["title"] == {"old": "Old", "new": "New"}


@pytest.mark.django_db
def test_log_action_with_changes_and_existing_data():
    """When both data and old_data/new_data are provided, changes are merged
    into the existing data dict."""
    with scopes_disabled():
        submission = SubmissionFactory()

    log = submission.log_action(
        "pretalx.submission.update",
        data={"extra": "info"},
        old_data={"title": "Old"},
        new_data={"title": "New"},
    )

    assert log.data["extra"] == "info"
    assert log.data["changes"]["title"] == {"old": "Old", "new": "New"}


@pytest.mark.django_db
def test_log_action_no_changes_but_with_data():
    """When old_data and new_data produce no changes but data is provided,
    the log is still created with the data."""
    with scopes_disabled():
        submission = SubmissionFactory()

    log = submission.log_action(
        "pretalx.submission.update",
        data={"note": "manual edit"},
        old_data={"title": "Same"},
        new_data={"title": "Same"},
    )

    assert log is not None
    assert log.data == {"note": "manual edit"}
    assert "changes" not in log.data


@pytest.mark.django_db
def test_log_action_with_identical_old_and_new_data_returns_none():
    """When old_data and new_data are identical and no extra data is provided,
    nothing is logged."""
    with scopes_disabled():
        submission = SubmissionFactory()

    result = submission.log_action(
        "pretalx.submission.update",
        old_data={"title": "Same"},
        new_data={"title": "Same"},
    )

    assert result is None


@pytest.mark.django_db
def test_compute_changes_both_none():
    with scopes_disabled():
        submission = SubmissionFactory()

    changes = submission._compute_changes(None, None)

    assert changes == {}


@pytest.mark.django_db
def test_compute_changes_identical_truthy_values():
    with scopes_disabled():
        submission = SubmissionFactory()

    data = {"title": "Same Title", "state": "submitted"}
    changes = submission._compute_changes(data, data)

    assert changes == {}


@pytest.mark.django_db
def test_compute_changes_ignores_both_falsy():
    """When both old and new are falsy (empty string and None), the key is
    skipped."""
    with scopes_disabled():
        submission = SubmissionFactory()

    changes = submission._compute_changes({"key": ""}, {"key": None})

    assert changes == {}


@pytest.mark.django_db
def test_compute_changes_mixed_keys():
    """Changed, unchanged, and None-to-truthy keys are handled correctly in a
    single call."""
    with scopes_disabled():
        submission = SubmissionFactory()

    old_data = {"title": "Old Title", "state": "submitted", "track": None}
    new_data = {"title": "New Title", "state": "submitted", "track": 1}
    changes = submission._compute_changes(old_data, new_data)

    assert changes["title"] == {"old": "Old Title", "new": "New Title"}
    assert "state" not in changes
    assert changes["track"] == {"old": None, "new": 1}


@pytest.mark.django_db
def test_compute_changes_tracks_additions():
    with scopes_disabled():
        submission = SubmissionFactory()

    changes = submission._compute_changes({}, {"title": "New"})

    assert changes == {"title": {"old": None, "new": "New"}}


@pytest.mark.django_db
def test_compute_changes_tracks_removals():
    with scopes_disabled():
        submission = SubmissionFactory()

    changes = submission._compute_changes({"title": "Old"}, {})

    assert changes == {"title": {"old": "Old", "new": None}}


@pytest.mark.django_db
def test_get_instance_data_excludes_sensitive_and_auto_fields():
    with scopes_disabled():
        submission = SubmissionFactory()
        data = submission.get_instance_data()

    for excluded in (
        "created",
        "updated",
        "is_active",
        "last_login",
        "user",
        "event",
        "code",
    ):
        assert excluded not in data
    for key in SENSITIVE_KEYS:
        assert key not in data


@pytest.mark.django_db
def test_get_instance_data_includes_regular_fields():
    with scopes_disabled():
        submission = SubmissionFactory(title="My Talk")
        data = submission.get_instance_data()

    assert data["title"] == "My Talk"


@pytest.mark.django_db
def test_get_instance_data_serializes_foreign_keys_as_pk():
    with scopes_disabled():
        submission = SubmissionFactory()
        data = submission.get_instance_data()

    assert data["submission_type"] == submission.submission_type.pk


@pytest.mark.django_db
def test_get_instance_data_serializes_i18n_string_dict():
    """LazyI18nString fields with dict data are serialized as filtered dicts."""
    with scopes_disabled():
        track = TrackFactory(name={"en": "English Name", "de": "German Name"})
        track.refresh_from_db()
        data = track.get_instance_data()

    assert data["name"] == {"en": "English Name", "de": "German Name"}


@pytest.mark.django_db
def test_get_instance_data_serializes_i18n_string_plain():
    """LazyI18nString fields with a plain string are serialized as str."""
    with scopes_disabled():
        track = TrackFactory(name="Simple Name")
        track.refresh_from_db()
        data = track.get_instance_data()

    assert data["name"] == "Simple Name"


@pytest.mark.django_db
def test_get_instance_data_serializes_uuid_field():
    """UUIDField values are serialized as strings."""
    with scopes_disabled():
        room = RoomFactory()
        room.guid = uuid.uuid4()
        room.save(update_fields=["guid"])
        room.refresh_from_db()
        data = room.get_instance_data()

    assert data["guid"] == str(room.guid)


@pytest.mark.django_db
def test_logged_actions_returns_matching_logs():
    with scopes_disabled():
        submission = SubmissionFactory()
    log = submission.log_action("pretalx.submission.create")

    with scopes_disabled():
        actions = list(submission.logged_actions())

    assert actions == [log]


@pytest.mark.django_db
def test_logmixin_delete_logs_parent_action():
    """When a LogMixin model with log_parent and log_prefix is deleted, a
    delete action is logged on the parent."""
    with scopes_disabled():
        track = TrackFactory()
        event = track.event
        expected_action = f"{track.log_prefix}.delete"

    with scopes_disabled():
        track.delete()

    with scopes_disabled():
        log = ActivityLog.objects.get(
            content_type=ContentType.objects.get_for_model(type(event)),
            object_id=event.pk,
            action_type=expected_action,
        )
        assert log.event == event


@pytest.mark.django_db
def test_logmixin_delete_skip_log():
    """When skip_log=True, no delete log is created."""
    with scopes_disabled():
        track = TrackFactory()
        event = track.event
        ct = ContentType.objects.get_for_model(type(event))
        initial_count = ActivityLog.objects.filter(
            content_type=ct, object_id=event.pk
        ).count()

    with scopes_disabled():
        track.delete(skip_log=True)

    with scopes_disabled():
        assert (
            ActivityLog.objects.filter(content_type=ct, object_id=event.pk).count()
            == initial_count
        )


@pytest.mark.django_db
def test_generate_code_assigns_code_on_save():
    with scopes_disabled():
        submission = SubmissionFactory()

    assert len(submission.code) == 6


@pytest.mark.django_db
def test_generate_code_does_not_overwrite_existing_code():
    with scopes_disabled():
        submission = SubmissionFactory()
    original_code = submission.code

    with scopes_disabled():
        submission.save()

    assert submission.code == original_code


@pytest.mark.django_db
def test_generate_code_save_with_update_fields():
    """When save() is called with update_fields on an object without a code,
    the code field is added to update_fields."""
    with scopes_disabled():
        submission = SubmissionFactory()
        submission.code = None
        submission.save(update_fields=["title"])

    assert len(submission.code) == 6


@pytest.mark.django_db
def test_generate_code_charset():
    """Generated codes only use allowed characters."""
    allowed = set(Submission.code_charset)

    with scopes_disabled():
        submission = SubmissionFactory()

    assert all(c in allowed for c in submission.code)


@pytest.mark.django_db
def test_generate_code_class_method():
    code = Submission.generate_code()

    assert len(code) == 6
    assert all(c in Submission.code_charset for c in code)


@pytest.mark.django_db
def test_generate_code_class_method_custom_length():
    code = Submission.generate_code(length=10)

    assert len(code) == 10


@pytest.mark.django_db
def test_generate_unique_codes():
    codes = Submission.generate_unique_codes(5)

    assert len(codes) == 5
    assert len(set(codes)) == 5


@pytest.mark.django_db
def test_generate_unique_codes_avoids_existing():
    """Generated codes do not collide with existing database codes."""
    with scopes_disabled():
        submission = SubmissionFactory()

    codes = Submission.generate_unique_codes(3)

    assert submission.code not in codes


@pytest.mark.django_db
def test_generate_unique_codes_with_scope():
    """Scoped code generation requires scope kwargs."""
    with scopes_disabled():
        question = QuestionFactory()

    codes = Question.generate_unique_codes(3, event=question.event)

    assert len(codes) == 3
    assert len(set(codes)) == 3


@pytest.mark.django_db
def test_generate_unique_codes_missing_scope_raises():
    with pytest.raises(ValueError, match="Missing required scope field"):
        Question.generate_unique_codes(3)


@pytest.mark.django_db
def test_assign_code_retries_on_collision(monkeypatch):
    """assign_code retries when the generated code already exists in the database."""
    with scopes_disabled():
        existing = SubmissionFactory()
    existing_code = existing.code

    # Monkeypatch is necessary because code generation is random — we cannot
    # reliably trigger a collision without controlling the output.
    codes = iter([existing_code, existing_code, "XXXXXX"])
    monkeypatch.setattr(
        "pretalx.common.models.mixins.get_random_string",
        lambda *args, **kwargs: next(codes),
    )

    with scopes_disabled():
        new = SubmissionFactory()

    assert new.code == "XXXXXX"


@pytest.mark.django_db
def test_generate_unique_codes_retries_on_collision(monkeypatch):
    """generate_unique_codes skips codes that collide with existing database
    entries or with earlier codes in the same batch."""
    with scopes_disabled():
        existing = SubmissionFactory()
    existing_code = existing.code

    # Monkeypatch is necessary because code generation is random — we cannot
    # reliably trigger a collision without controlling the output.
    codes = iter([existing_code, "AAAAAA", "AAAAAA", "BBBBBB"])
    monkeypatch.setattr(
        "pretalx.common.models.mixins.get_random_string",
        lambda *args, **kwargs: next(codes),
    )

    result = Submission.generate_unique_codes(2)

    assert result == ["AAAAAA", "BBBBBB"]


@pytest.mark.django_db
def test_generate_code_save_retries_on_integrity_error(monkeypatch):
    """When a TOCTOU race causes an IntegrityError on save, the code is
    regenerated and save is retried."""
    with scopes_disabled():
        existing = SubmissionFactory()
    existing_code = existing.code

    call_count = 0
    original_assign = Submission.assign_code

    def assign_with_collision(self, length=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            self.code = existing_code
        else:
            original_assign(self, length=length)

    # Monkeypatch is necessary because the race condition occurs between
    # assign_code's exists() check and save() — impossible to reproduce
    # without controlling the timing of concurrent processes.
    monkeypatch.setattr(Submission, "assign_code", assign_with_collision)

    with scopes_disabled():
        new = SubmissionFactory()

    assert new.code != existing_code
    assert len(new.code) == 6
    assert call_count == 2


@pytest.mark.django_db
def test_generate_code_save_raises_after_max_integrity_errors(monkeypatch):
    """After 3 consecutive IntegrityErrors, the exception is re-raised."""
    with scopes_disabled():
        existing = SubmissionFactory()
    existing_code = existing.code

    # Monkeypatch is necessary because the race condition occurs between
    # assign_code's exists() check and save() — impossible to reproduce
    # without controlling the timing of concurrent processes.
    monkeypatch.setattr(
        Submission,
        "assign_code",
        lambda self, length=None: setattr(self, "code", existing_code),
    )

    with pytest.raises(IntegrityError), scopes_disabled():
        SubmissionFactory()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("move_index", "up", "expected_positions"),
    ((1, True, (1, 0)), (0, False, (1, 0)), (0, True, (0, 1)), (1, False, (0, 1))),
    ids=(
        "move_up",
        "move_down",
        "move_up_at_top_is_noop",
        "move_down_at_bottom_is_noop",
    ),
)
def test_ordered_model_move(move_index, up, expected_positions):
    with scopes_disabled():
        event = EventFactory()
        tracks = [TrackFactory(event=event, position=i) for i in range(2)]

    with scopes_disabled():
        tracks[move_index].move(up=up)
        for track in tracks:
            track.refresh_from_db()

    assert (tracks[0].position, tracks[1].position) == expected_positions


@pytest.mark.django_db
def test_file_cleanup_mixin_delete_removes_files(tmp_path, settings):
    """FileCleanupMixin.delete() removes associated files from storage."""
    settings.MEDIA_ROOT = str(tmp_path)
    with scopes_disabled():
        user = UserFactory()
    picture = ProfilePicture.objects.create(user=user)
    picture.avatar.save("test.png", ContentFile(b"\x89PNG\r\n\x1a\n"), save=True)
    file_path = Path(picture.avatar.path)

    assert file_path.exists()

    picture.delete()

    assert not file_path.exists()


@pytest.mark.django_db
def test_file_cleanup_mixin_save_removes_old_file_on_change(tmp_path, settings):
    """When a file field changes, the old file is deleted via the cleanup task
    (which runs synchronously in eager mode)."""
    settings.MEDIA_ROOT = str(tmp_path)
    with scopes_disabled():
        user = UserFactory()
    picture = ProfilePicture.objects.create(user=user)
    picture.avatar.save("old.png", ContentFile(b"\x89PNG\r\n\x1a\n"), save=True)
    old_path = Path(picture.avatar.path)

    assert old_path.exists()

    picture.avatar.save("new.png", ContentFile(b"\x89PNG\r\n\x1a\n"), save=True)

    assert Path(picture.avatar.path).exists()
    assert not old_path.exists()


@pytest.mark.django_db
def test_file_cleanup_mixin_save_no_cleanup_on_new_instance(tmp_path, settings):
    """When saving a new instance (no pk yet), no cleanup is attempted."""
    settings.MEDIA_ROOT = str(tmp_path)
    with scopes_disabled():
        user = UserFactory()

    picture = ProfilePicture(user=user)
    picture.avatar = ContentFile(b"\x89PNG\r\n\x1a\n", name="test.png")
    picture.save()

    assert Path(picture.avatar.path).exists()


@pytest.mark.django_db
def test_file_cleanup_mixin_save_no_cleanup_when_update_fields_excludes_file(
    tmp_path, settings
):
    """When update_fields is specified and doesn't include file fields, no
    cleanup is attempted."""
    settings.MEDIA_ROOT = str(tmp_path)
    with scopes_disabled():
        user = UserFactory()
    picture = ProfilePicture.objects.create(user=user)
    picture.avatar.save("test.png", ContentFile(b"\x89PNG\r\n\x1a\n"), save=True)

    # Saving with update_fields that don't include file fields should skip cleanup
    picture.save(update_fields=["updated"])


@pytest.mark.django_db
def test_file_cleanup_mixin_save_object_does_not_exist(tmp_path, settings):
    """When the pre-save instance lookup fails (row deleted between check
    and save), save proceeds without cleanup."""
    settings.MEDIA_ROOT = str(tmp_path)
    with scopes_disabled():
        user = UserFactory()
    picture = ProfilePicture.objects.create(user=user)
    picture.avatar.save("test.png", ContentFile(b"\x89PNG\r\n\x1a\n"), save=True)
    file_path = Path(picture.avatar.path)
    pk = picture.pk

    ProfilePicture.objects.filter(pk=pk).delete()

    picture.save(force_insert=True)

    assert picture.pk == pk
    assert file_path.exists()


@pytest.mark.django_db
def test_file_cleanup_mixin_process_image(tmp_path, settings, make_image):
    """process_image dispatches a Celery task that processes the image file."""
    settings.MEDIA_ROOT = str(tmp_path)
    with scopes_disabled():
        user = UserFactory()
    picture = ProfilePicture.objects.create(user=user)
    picture.avatar.save("test.png", make_image(), save=True)

    picture.process_image("avatar", generate_thumbnail=True)

    picture.refresh_from_db()
    assert picture.avatar
