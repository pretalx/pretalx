import datetime as dt
import json

import pytest
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms import ValidationError
from django_scopes import scopes_disabled

from pretalx.common.forms.fields import (
    AvailabilitiesField,
    ColorField,
    CountableOption,
    ExtensionFileField,
    HoneypotField,
    ImageField,
    NewPasswordConfirmationField,
    NewPasswordField,
    ProfilePictureField,
    SizeFileField,
    SizeFileInput,
    SubmissionTypeField,
)
from pretalx.person.models import ProfilePicture
from pretalx.schedule.models import Availability
from tests.factories import (
    EventFactory,
    RoomFactory,
    SpeakerFactory,
    SubmissionTypeFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


def test_countable_option_str_returns_name():
    option = CountableOption("Workshop", 5)
    assert str(option) == "Workshop"


def test_new_password_field_uses_validate_password():
    field = NewPasswordField()
    assert validate_password in field.default_validators


def test_new_password_confirmation_field_sets_confirm_with():
    field = NewPasswordConfirmationField(confirm_with="id_password")
    assert field.widget.confirm_with == "id_password"


@pytest.mark.parametrize(
    ("kwargs", "expected_size"),
    (
        ({"max_size": 1024}, "1.0KB"),
        ({}, "10.0MB"),
        ({"max_size": 0, "fallback": False}, "0.0B"),
    ),
    ids=("explicit_size", "fallback_to_default", "no_fallback"),
)
def test_size_file_input_get_size_warning(kwargs, expected_size):
    warning = SizeFileInput.get_size_warning(**kwargs)
    assert expected_size in warning


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    (
        ({}, settings.FILE_UPLOAD_DEFAULT_LIMIT),
        ({"max_size": 2048}, 2048),
        ({"max_size": None}, None),
    ),
    ids=("default", "custom", "explicit_none"),
)
def test_size_file_field_init_max_size(kwargs, expected):
    field = SizeFileField(**kwargs)
    assert field.max_size == expected


def test_size_file_field_sets_widget_data_attrs():
    field = SizeFileField(max_size=5000)
    assert field.widget.attrs["data-maxsize"] == 5000
    assert field.widget.attrs["data-sizewarning"]


def test_size_file_field_help_text_includes_size_warning():
    field = SizeFileField(max_size=1024)
    assert "1.0KB" in field.help_text


def test_size_file_field_validate_accepts_small_file():
    field = SizeFileField(max_size=10000, required=False)
    small_file = SimpleUploadedFile(
        "test.txt", b"small content", content_type="text/plain"
    )
    field.validate(small_file)


def test_size_file_field_validate_rejects_oversized_file():
    field = SizeFileField(max_size=10, required=False)
    big_file = SimpleUploadedFile("test.txt", b"x" * 100, content_type="text/plain")
    with pytest.raises(ValidationError):
        field.validate(big_file)


def test_size_file_field_validate_skips_non_upload_values():
    """Non-UploadedFile values (like empty strings) pass size validation."""
    field = SizeFileField(max_size=10, required=False)
    field.validate("")


def test_size_file_field_validate_skips_when_no_max_size():
    field = SizeFileField(max_size=None, required=False)
    big_file = SimpleUploadedFile("test.txt", b"x" * 10000, content_type="text/plain")
    field.validate(big_file)


def test_extension_file_input_sets_accept_attribute():
    extensions = {
        ".pdf": ["application/pdf", ".pdf"],
        ".doc": ["application/msword", ".doc"],
    }
    field = ExtensionFileField(extensions=extensions, required=False)
    accept = field.widget.attrs["accept"]
    assert "application/pdf" in accept
    assert ".pdf" in accept
    assert "application/msword" in accept


@pytest.mark.parametrize(
    "filename", ("doc.pdf", "doc.PDF"), ids=("lowercase", "uppercase")
)
def test_extension_file_field_validate_accepts_valid_extension(filename):
    extensions = {".pdf": ["application/pdf"]}
    field = ExtensionFileField(extensions=extensions, required=False)
    pdf_file = SimpleUploadedFile(filename, b"content", content_type="application/pdf")
    field.validate(pdf_file)


def test_extension_file_field_validate_rejects_invalid_extension():
    extensions = {".pdf": ["application/pdf"]}
    field = ExtensionFileField(extensions=extensions, required=False)
    exe_file = SimpleUploadedFile(
        "bad.exe", b"content", content_type="application/octet-stream"
    )
    with pytest.raises(ValidationError) as exc_info:
        field.validate(exe_file)
    assert ".exe" in str(exc_info.value)


def test_extension_file_field_validate_empty_value_passes():
    extensions = {".pdf": ["application/pdf"]}
    field = ExtensionFileField(extensions=extensions, required=False)
    field.validate("")


def test_image_field_uses_image_extensions():
    field = ImageField(required=False)
    accept = field.widget.attrs["accept"]
    assert "image/png" in accept
    assert "image/jpeg" in accept


def test_image_field_rejects_non_image():
    field = ImageField(required=False)
    txt_file = SimpleUploadedFile("bad.txt", b"content", content_type="text/plain")
    with pytest.raises(ValidationError):
        field.validate(txt_file)


def test_profile_picture_field_set_widget_data():
    field = ProfilePictureField(user="some_user", upload_only=True)
    field.set_widget_data()
    assert field.widget.user == "some_user"
    assert field.widget.upload_only is True


def test_profile_picture_field_clean_non_dict_returns_none():
    field = ProfilePictureField(required=False)
    assert field.clean("not a dict") is None


def test_profile_picture_field_clean_keep_without_current_required():
    field = ProfilePictureField(required=True, current_picture=None)
    with pytest.raises(ValidationError) as exc_info:
        field.clean({"action": "keep"})
    assert exc_info.value.code == "required"


def test_profile_picture_field_clean_keep_with_current_picture():
    field = ProfilePictureField(required=True, current_picture="existing")
    result = field.clean({"action": "keep"})
    assert result is None
    assert field._cleaned_value is None


def test_profile_picture_field_clean_keep_not_required():
    field = ProfilePictureField(required=False, current_picture=None)
    result = field.clean({"action": "keep"})
    assert result is None


def test_profile_picture_field_clean_remove_when_required():
    field = ProfilePictureField(required=True)
    with pytest.raises(ValidationError) as exc_info:
        field.clean({"action": "remove"})
    assert exc_info.value.code == "required"


def test_profile_picture_field_clean_remove_when_not_required():
    field = ProfilePictureField(required=False)
    result = field.clean({"action": "remove"})
    assert result is False
    assert field._cleaned_value is False


def test_profile_picture_field_clean_upload_no_file():
    field = ProfilePictureField(required=False)
    with pytest.raises(ValidationError) as exc_info:
        field.clean({"action": "upload", "file": None})
    assert exc_info.value.code == "required"


def test_profile_picture_field_clean_upload_invalid_content_type():
    field = ProfilePictureField(required=False)
    bad_file = SimpleUploadedFile("test.txt", b"data", content_type="text/plain")
    with pytest.raises(ValidationError) as exc_info:
        field.clean({"action": "upload", "file": bad_file})
    assert exc_info.value.code == "invalid"


def test_profile_picture_field_clean_upload_oversized_file():
    field = ProfilePictureField(required=False)
    big_data = b"x" * (settings.FILE_UPLOAD_DEFAULT_LIMIT + 1)
    big_file = SimpleUploadedFile("big.png", big_data, content_type="image/png")
    with pytest.raises(ValidationError) as exc_info:
        field.clean({"action": "upload", "file": big_file})
    assert exc_info.value.code == "invalid"


def test_profile_picture_field_clean_upload_valid_file():
    field = ProfilePictureField(required=False)
    valid_file = SimpleUploadedFile("avatar.png", b"x" * 100, content_type="image/png")
    result = field.clean({"action": "upload", "file": valid_file})
    assert result == valid_file
    assert field._cleaned_value == valid_file


@pytest.mark.django_db
def test_profile_picture_field_clean_select_valid_picture():
    user = UserFactory()
    picture = ProfilePicture.objects.create(user=user)
    field = ProfilePictureField(required=False, user=user)

    result = field.clean({"action": f"select_{picture.pk}"})

    assert result == picture
    assert field._cleaned_value == picture


@pytest.mark.django_db
@pytest.mark.parametrize(
    "pk_suffix", ("99999", "abc"), ids=("nonexistent", "non_numeric")
)
def test_profile_picture_field_clean_select_invalid_pk(pk_suffix):
    user = UserFactory()
    field = ProfilePictureField(required=False, user=user)

    with pytest.raises(ValidationError) as exc_info:
        field.clean({"action": f"select_{pk_suffix}"})
    assert exc_info.value.code == "invalid"


@pytest.mark.django_db
def test_profile_picture_field_clean_select_other_users_picture():
    user = UserFactory()
    other_user = UserFactory()
    picture = ProfilePicture.objects.create(user=other_user)
    field = ProfilePictureField(required=False, user=user)

    with pytest.raises(ValidationError) as exc_info:
        field.clean({"action": f"select_{picture.pk}"})
    assert exc_info.value.code == "invalid"


def test_profile_picture_field_clean_select_when_upload_only():
    field = ProfilePictureField(required=False, upload_only=True)
    with pytest.raises(ValidationError) as exc_info:
        field.clean({"action": "select_1"})
    assert exc_info.value.code == "invalid"


def test_profile_picture_field_has_changed_non_dict_returns_false():
    field = ProfilePictureField()
    assert field.has_changed(None, "not a dict") is False


@pytest.mark.parametrize(
    ("action", "expected"),
    (("keep", False), ("remove", True), ("upload", True), ("select_1", True)),
)
def test_profile_picture_field_has_changed(action, expected):
    field = ProfilePictureField()
    assert field.has_changed(None, {"action": action}) is expected


@pytest.mark.django_db
def test_profile_picture_field_save_none_does_nothing():
    """When _cleaned_value is None (keep), save() is a no-op."""
    user = UserFactory()
    field = ProfilePictureField()
    field._cleaned_value = None
    field.save(instance=user, user=user)


def test_color_field_accepts_valid_hex():
    field = ColorField()
    assert field.clean("#ff0000") == "#ff0000"


def test_color_field_accepts_short_hex():
    field = ColorField()
    assert field.clean("#f00") == "#f00"


@pytest.mark.parametrize(
    "value",
    ("not-a-color", "#xyz", "#12345", "ff0000", "#1234567"),
    ids=("text", "bad_chars", "5_digits", "no_hash", "too_long"),
)
def test_color_field_rejects_invalid_hex(value):
    field = ColorField()
    with pytest.raises(ValidationError):
        field.clean(value)


def test_color_field_widget_attrs_include_pattern():
    field = ColorField()
    attrs = field.widget_attrs(field.widget)
    assert "pattern" in attrs


@pytest.mark.django_db
def test_submission_type_field_label_shows_duration_when_not_required():
    """When cfp does not require duration, label includes the duration."""
    with scopes_disabled():
        sub_type = SubmissionTypeFactory(default_duration=30)
        sub_type.event.cfp.fields["duration"] = {"visibility": "do_not_ask"}
        sub_type.event.cfp.save()

    field = SubmissionTypeField(queryset=type(sub_type).objects.none())
    label = field.label_from_instance(sub_type)

    assert label == str(sub_type)
    assert "30" in label


@pytest.mark.django_db
def test_submission_type_field_label_hides_duration_when_required():
    """When cfp requires duration, label shows only the name."""
    with scopes_disabled():
        sub_type = SubmissionTypeFactory(default_duration=30)
        sub_type.event.cfp.fields["duration"] = {"visibility": "required"}
        sub_type.event.cfp.save()

    field = SubmissionTypeField(queryset=type(sub_type).objects.none())
    label = field.label_from_instance(sub_type)

    assert label == str(sub_type.name)


def test_honeypot_field_not_required():
    field = HoneypotField()
    assert field.required is False


def test_honeypot_field_validate_raises_on_true():
    field = HoneypotField()
    with pytest.raises(ValidationError):
        field.validate(True)


def test_honeypot_field_validate_passes_on_false():
    field = HoneypotField()
    field.validate(False)


@pytest.mark.django_db
def test_availabilities_field_init_with_event_sets_initial(event):
    room = RoomFactory(event=event)
    with scopes_disabled():
        Availability.objects.create(
            event=event, room=room, start=event.datetime_from, end=event.datetime_to
        )
        field = AvailabilitiesField(event=event, instance=room)

    initial = json.loads(field.initial)
    assert "availabilities" in initial
    assert "event" in initial
    assert initial["event"]["timezone"] == event.timezone


@pytest.mark.django_db
def test_availabilities_field_set_initial_from_instance(event):
    field = AvailabilitiesField(event=event, instance=None)
    field.set_initial_from_instance()
    initial = json.loads(field.initial)
    assert "availabilities" in initial


@pytest.mark.django_db
def test_availabilities_field_set_initial_noop_without_event():
    field = AvailabilitiesField(event=None, instance=None)
    field.set_initial_from_instance()
    assert not field.initial


def test_availabilities_field_get_event_context_without_event():
    field = AvailabilitiesField(event=None)
    assert field._get_event_context() == {}


@pytest.mark.django_db
def test_availabilities_field_get_event_context_with_event(event):
    field = AvailabilitiesField(event=event)
    ctx = field._get_event_context()
    assert ctx["event"]["timezone"] == event.timezone
    assert ctx["event"]["date_from"] == str(event.date_from)
    assert ctx["event"]["date_to"] == str(event.date_to)


@pytest.mark.django_db
def test_availabilities_field_get_event_context_with_resolution(event):
    field = AvailabilitiesField(event=event, resolution=15)
    ctx = field._get_event_context()
    assert ctx["resolution"] == 15


@pytest.mark.django_db
def test_availabilities_field_get_event_context_includes_room_constraints(event):
    """When instance is not a Room and rooms have availabilities,
    the context includes merged room constraints."""
    with scopes_disabled():
        room = RoomFactory(event=event)
        Availability.objects.create(
            event=event, room=room, start=event.datetime_from, end=event.datetime_to
        )
        speaker = SpeakerFactory(event=event)
    field = AvailabilitiesField(event=event)
    field.instance = speaker
    with scopes_disabled():
        ctx = field._get_event_context()
    assert "constraints" in ctx
    assert len(ctx["constraints"]) == 1


@pytest.mark.django_db
def test_availabilities_field_get_event_context_no_constraints_for_room(event):
    """When the instance is a Room, room constraints are not included."""
    room = RoomFactory(event=event)
    with scopes_disabled():
        field = AvailabilitiesField(event=event, instance=room)
    ctx = field._get_event_context()
    assert "constraints" not in ctx


@pytest.mark.django_db
def test_availabilities_field_prepare_value_adds_event_context(event):
    field = AvailabilitiesField(event=event)
    data = json.dumps({"availabilities": []})
    result = field.prepare_value(data)
    parsed = json.loads(result)
    assert "event" in parsed


@pytest.mark.django_db
def test_availabilities_field_prepare_value_preserves_existing_event(event):
    field = AvailabilitiesField(event=event)
    data = json.dumps({"availabilities": [], "event": {"timezone": "custom"}})
    result = field.prepare_value(data)
    parsed = json.loads(result)
    assert parsed["event"]["timezone"] == "custom"


def test_availabilities_field_prepare_value_non_string():
    field = AvailabilitiesField(event=None)
    result = field.prepare_value(42)
    assert result == 42


def test_availabilities_field_prepare_value_invalid_json():
    field = AvailabilitiesField(event=EventFactory.build())
    result = field.prepare_value("not json{{{")
    assert result == "not json{{{"


@pytest.mark.django_db
def test_availabilities_field_clean_valid_json(event):
    start = dt.datetime.combine(event.date_from, dt.time(9, 0), tzinfo=event.tz)
    end = dt.datetime.combine(event.date_from, dt.time(17, 0), tzinfo=event.tz)
    data = json.dumps(
        {"availabilities": [{"start": start.isoformat(), "end": end.isoformat()}]}
    )
    field = AvailabilitiesField(event=event, required=False)

    result = field.clean(data)

    assert len(result) == 1
    assert all(isinstance(a, Availability) for a in result)


@pytest.mark.django_db
def test_availabilities_field_clean_empty_required(event):
    field = AvailabilitiesField(event=event, required=True)
    with pytest.raises(ValidationError):
        field.clean("")


@pytest.mark.django_db
def test_availabilities_field_clean_empty_not_required(event):
    field = AvailabilitiesField(event=event, required=False)
    result = field.clean("")
    assert result == []


@pytest.mark.django_db
def test_availabilities_field_clean_invalid_json(event):
    field = AvailabilitiesField(event=event, required=False)
    with pytest.raises(ValidationError) as exc_info:
        field.clean("not valid json")
    assert exc_info.value.code == "invalid_json"


@pytest.mark.django_db
def test_availabilities_field_clean_non_dict_json(event):
    field = AvailabilitiesField(event=event, required=False)
    with pytest.raises(ValidationError) as exc_info:
        field.clean(json.dumps([1, 2, 3]))
    assert exc_info.value.code == "invalid_format"


@pytest.mark.django_db
def test_availabilities_field_clean_availabilities_not_list(event):
    field = AvailabilitiesField(event=event, required=False)
    with pytest.raises(ValidationError) as exc_info:
        field.clean(json.dumps({"availabilities": "not a list"}))
    assert exc_info.value.code == "invalid_format"


@pytest.mark.django_db
def test_availabilities_field_clean_empty_availabilities_required(event):
    field = AvailabilitiesField(event=event, required=True)
    with pytest.raises(ValidationError):
        field.clean(json.dumps({"availabilities": []}))


@pytest.mark.django_db
def test_availabilities_field_clean_availability_not_dict(event):
    field = AvailabilitiesField(event=event, required=False)
    with pytest.raises(ValidationError) as exc_info:
        field.clean(json.dumps({"availabilities": ["not a dict"]}))
    assert exc_info.value.code == "invalid_availability_format"


@pytest.mark.django_db
def test_availabilities_field_clean_availability_extra_keys(event):
    field = AvailabilitiesField(event=event, required=False)
    start = dt.datetime.combine(event.date_from, dt.time(9, 0), tzinfo=event.tz)
    end = dt.datetime.combine(event.date_from, dt.time(17, 0), tzinfo=event.tz)
    with pytest.raises(ValidationError) as exc_info:
        field.clean(
            json.dumps(
                {
                    "availabilities": [
                        {
                            "start": start.isoformat(),
                            "end": end.isoformat(),
                            "extra": "bad",
                        }
                    ]
                }
            )
        )
    assert exc_info.value.code == "invalid_availability_format"


@pytest.mark.django_db
def test_availabilities_field_clean_strips_id_and_allday(event):
    """id and allDay keys are stripped before validation."""
    start = dt.datetime.combine(event.date_from, dt.time(9, 0), tzinfo=event.tz)
    end = dt.datetime.combine(event.date_from, dt.time(17, 0), tzinfo=event.tz)
    data = json.dumps(
        {
            "availabilities": [
                {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "id": 42,
                    "allDay": True,
                }
            ]
        }
    )
    field = AvailabilitiesField(event=event, required=False)

    result = field.clean(data)

    assert len(result) == 1


@pytest.mark.django_db
def test_availabilities_field_clean_invalid_date_string(event):
    field = AvailabilitiesField(event=event, required=False)
    with pytest.raises(ValidationError) as exc_info:
        field.clean(
            json.dumps({"availabilities": [{"start": "not-a-date", "end": "also-not"}]})
        )
    assert exc_info.value.code == "invalid_date"


@pytest.mark.django_db
def test_availabilities_field_clean_clamps_to_event_dates(event):
    """Availability times are clamped to the event's date range."""
    early = dt.datetime.combine(
        event.date_from - dt.timedelta(days=5), dt.time(9, 0), tzinfo=event.tz
    )
    late = dt.datetime.combine(
        event.date_to + dt.timedelta(days=5), dt.time(17, 0), tzinfo=event.tz
    )
    data = json.dumps(
        {"availabilities": [{"start": early.isoformat(), "end": late.isoformat()}]}
    )
    field = AvailabilitiesField(event=event, required=False)

    result = field.clean(data)

    assert len(result) == 1
    event_start = dt.datetime.combine(event.date_from, dt.time(), tzinfo=event.tz)
    event_end = dt.datetime.combine(
        event.date_to, dt.time(), tzinfo=event.tz
    ) + dt.timedelta(days=1)
    assert result[0].start == event_start
    assert result[0].end == event_end


@pytest.mark.django_db
def test_availabilities_field_clean_list_input(event):
    """clean() accepts a list directly and wraps it in an availabilities dict."""
    start = dt.datetime.combine(event.date_from, dt.time(9, 0), tzinfo=event.tz)
    end = dt.datetime.combine(event.date_from, dt.time(17, 0), tzinfo=event.tz)

    result = AvailabilitiesField(event=event, required=False).clean(
        [{"start": start.isoformat(), "end": end.isoformat()}]
    )

    assert len(result) == 1


@pytest.mark.django_db
def test_availabilities_field_clean_dict_input(event):
    """clean() accepts a dict directly and converts to JSON."""
    start = dt.datetime.combine(event.date_from, dt.time(9, 0), tzinfo=event.tz)
    end = dt.datetime.combine(event.date_from, dt.time(17, 0), tzinfo=event.tz)

    result = AvailabilitiesField(event=event, required=False).clean(
        {"availabilities": [{"start": start.isoformat(), "end": end.isoformat()}]}
    )

    assert len(result) == 1


@pytest.mark.django_db
def test_availabilities_field_parse_datetime_naive_gets_event_tz(event):
    """Naive datetimes receive the event timezone."""
    field = AvailabilitiesField(event=event)
    result = field._parse_datetime("2025-06-15T09:00:00")
    assert result.tzinfo == event.tz


@pytest.mark.django_db
def test_availabilities_field_parse_datetime_invalid_raises(event):
    field = AvailabilitiesField(event=event)
    with pytest.raises(TypeError):
        field._parse_datetime("not a datetime")


@pytest.mark.django_db
def test_availabilities_field_serialize_empty_instance(event):
    field = AvailabilitiesField(event=event)
    result = field._serialize(event, None)
    parsed = json.loads(result)
    assert parsed["availabilities"] == []
    assert "event" in parsed


def test_profile_picture_field_clean_unknown_action_returns_none():
    """An unrecognised action falls through all branches and returns None."""
    field = ProfilePictureField(required=False)
    result = field.clean({"action": "unknown_action"})
    assert result is None


@pytest.mark.django_db
def test_profile_picture_field_save_upload_sets_avatar(make_image):
    """When _cleaned_value is an UploadedFile, save() delegates to set_avatar."""
    speaker = SpeakerFactory()
    user = speaker.user
    image = make_image("avatar.png")
    field = ProfilePictureField()
    field._cleaned_value = image

    field.save(instance=speaker, user=user)

    speaker.refresh_from_db()
    assert speaker.profile_picture is not None


@pytest.mark.django_db
def test_profile_picture_field_save_remove_clears_picture():
    """When _cleaned_value is False (remove), save() clears the picture."""
    speaker = SpeakerFactory()
    old_picture = ProfilePicture.objects.create(user=speaker.user)
    speaker.profile_picture = old_picture
    speaker.save(update_fields=["profile_picture"])
    field = ProfilePictureField()
    field._cleaned_value = False

    field.save(instance=speaker, user=speaker.user)

    speaker.refresh_from_db()
    assert speaker.profile_picture is None
    old_picture.refresh_from_db()
    assert old_picture.updated  # timestamp was bumped


@pytest.mark.django_db
def test_profile_picture_field_save_select_sets_new_picture():
    """When _cleaned_value is a ProfilePicture, save() assigns it and
    also sets it on the user if the user has no profile picture."""
    speaker = SpeakerFactory()
    user = speaker.user
    assert user.profile_picture is None
    new_picture = ProfilePicture.objects.create(user=user)
    old_picture = ProfilePicture.objects.create(user=user)
    speaker.profile_picture = old_picture
    speaker.save(update_fields=["profile_picture"])
    field = ProfilePictureField()
    field._cleaned_value = new_picture

    field.save(instance=speaker, user=user)

    speaker.refresh_from_db()
    user.refresh_from_db()
    assert speaker.profile_picture == new_picture
    assert user.profile_picture == new_picture
    old_picture.refresh_from_db()
    assert old_picture.updated  # timestamp was bumped


@pytest.mark.django_db
def test_profile_picture_field_save_remove_noop_when_already_none():
    """When _cleaned_value is False and instance already has no picture, save() is a no-op."""
    speaker = SpeakerFactory()
    assert speaker.profile_picture is None
    field = ProfilePictureField()
    field._cleaned_value = False

    field.save(instance=speaker, user=speaker.user)

    speaker.refresh_from_db()
    assert speaker.profile_picture is None


@pytest.mark.django_db
def test_profile_picture_field_save_select_without_old_picture():
    """When selecting a picture and instance had no prior picture, old_picture
    update is skipped but new picture is still assigned."""
    speaker = SpeakerFactory()
    user = speaker.user
    assert speaker.profile_picture is None
    assert user.profile_picture is None
    new_picture = ProfilePicture.objects.create(user=user)
    field = ProfilePictureField()
    field._cleaned_value = new_picture

    field.save(instance=speaker, user=user)

    speaker.refresh_from_db()
    user.refresh_from_db()
    assert speaker.profile_picture == new_picture
    assert user.profile_picture == new_picture


@pytest.mark.django_db
def test_submission_type_field_label_caches_show_duration():
    """After the first call, show_duration is cached and reused."""
    with scopes_disabled():
        sub_type = SubmissionTypeFactory(default_duration=30)
        sub_type.event.cfp.fields["duration"] = {"visibility": "do_not_ask"}
        sub_type.event.cfp.save()

    field = SubmissionTypeField(queryset=type(sub_type).objects.none())
    field.label_from_instance(sub_type)
    assert field.show_duration is True

    # Second call uses cached value (hits 284->286 branch)
    label = field.label_from_instance(sub_type)
    assert label == str(sub_type)


@pytest.mark.django_db
def test_availabilities_field_get_event_context_no_constraints_without_room_avails(
    event,
):
    """When instance is not a Room but no rooms have availabilities,
    no constraints key is added."""
    speaker = SpeakerFactory(event=event)
    field = AvailabilitiesField(event=event)
    field.instance = speaker

    with scopes_disabled():
        ctx = field._get_event_context()

    assert "constraints" not in ctx


@pytest.mark.django_db
def test_availabilities_field_validate_availability_with_datetime_objects(event):
    """When start/end are already datetime objects, they are used directly."""
    field = AvailabilitiesField(event=event, required=False)
    start = dt.datetime.combine(event.date_from, dt.time(9, 0), tzinfo=event.tz)
    end = dt.datetime.combine(event.date_from, dt.time(17, 0), tzinfo=event.tz)
    rawavail = {"start": start, "end": end}

    field._validate_availability(rawavail)

    assert rawavail["start"] == start
    assert rawavail["end"] == end
