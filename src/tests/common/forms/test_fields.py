# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import json
import warnings
import zoneinfo

import PIL.Image
import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms import ValidationError
from django.utils import timezone, translation

from pretalx.common.files import FILE_EXTENSIONS, IMAGE_EXTENSIONS
from pretalx.common.forms.fields import (
    AvailabilitiesField,
    ColorField,
    CssField,
    DateTimeField,
    ExtensionFileField,
    HoneypotField,
    ImageField,
    MultiDomainField,
    MultiEmailField,
    NewPasswordConfirmationField,
    NewPasswordField,
    ProfilePictureField,
    SizeFileField,
)
from pretalx.common.forms.widgets import MultiEmailInput
from pretalx.person.models import SpeakerProfile
from pretalx.schedule.models import Availability
from tests.factories import (
    AvailabilityFactory,
    EventFactory,
    ProfilePictureFactory,
    RoomFactory,
    SpeakerFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


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


@pytest.mark.parametrize(
    ("kwargs", "help_text"),
    (
        ({}, "Your password must contain at least 8 characters."),
        ({"help_text": "custom help"}, "custom help"),
    ),
    ids=("default_help", "custom_help"),
)
def test_new_password_field_exposes_min_length(kwargs, help_text):
    field = NewPasswordField(**kwargs)
    assert field.widget.attrs["minlength"] == 8
    assert field.help_text == help_text


def test_new_password_confirmation_field_exposes_min_length():
    field = NewPasswordConfirmationField()
    assert field.widget.attrs.get("minlength") == 8


def test_size_file_field_widget_data_and_lazy_help_text():
    field = SizeFileField(max_size=1024)

    with translation.override("en"):
        english = str(field.help_text)
    with translation.override("de"):
        german = str(field.help_text)

    assert field.widget.attrs["data-maxsize"] == 1024
    assert field.widget.attrs["data-sizewarning"]
    assert english != german
    assert "1.0KB" in english
    assert "1.0KB" in german


@pytest.mark.parametrize(
    ("max_size", "value"),
    (
        (10000, SimpleUploadedFile("test.txt", b"small content")),
        (10, ""),
        (None, SimpleUploadedFile("test.txt", b"x" * 10000)),
    ),
    ids=("small_file", "non_upload_value", "no_max_size"),
)
def test_size_file_field_validate_accepts(max_size, value):
    SizeFileField(max_size=max_size, required=False).validate(value)


def test_size_file_field_validate_rejects_oversized_file():
    field = SizeFileField(max_size=10, required=False)
    big_file = SimpleUploadedFile("test.txt", b"x" * 100, content_type="text/plain")
    with pytest.raises(ValidationError):
        field.validate(big_file)


def test_extension_file_input_sets_accept_attribute():
    extensions = {
        ".pdf": ["application/pdf", ".pdf"],
        ".doc": ["application/msword", ".doc"],
    }
    field = ExtensionFileField(extensions=extensions, required=False)
    assert set(field.widget.attrs["accept"].split(",")) == {
        ".doc",
        ".pdf",
        "application/pdf",
        "application/msword",
    }


@pytest.mark.parametrize(
    "value",
    (
        SimpleUploadedFile("doc.pdf", b"content", content_type="application/pdf"),
        SimpleUploadedFile("doc.PDF", b"content", content_type="application/pdf"),
        "",
    ),
    ids=("lowercase", "uppercase", "empty"),
)
def test_extension_file_field_validate_accepts(value):
    field = ExtensionFileField(extensions={".pdf": ["application/pdf"]}, required=False)
    field.validate(value)


def test_extension_file_field_validate_rejects_invalid_extension():
    extensions = {".pdf": ["application/pdf"]}
    field = ExtensionFileField(extensions=extensions, required=False)
    exe_file = SimpleUploadedFile(
        "bad.exe", b"content", content_type="application/octet-stream"
    )
    with pytest.raises(ValidationError) as exc_info:
        field.validate(exe_file)
    assert ".exe" in str(exc_info.value)


@pytest.mark.parametrize("extensions", (FILE_EXTENSIONS, IMAGE_EXTENSIONS))
def test_allow_list_keys_are_dotted_lowercase_extensions(extensions):
    for key in extensions:
        assert key == key.lower()
        assert key.startswith(".")


def test_image_field_uses_image_extensions():
    field = ImageField(required=False)
    accept = field.widget.attrs["accept"]
    assert "image/png" in accept
    assert "image/jpeg" in accept


@pytest.mark.parametrize(
    ("filename", "content_type", "body"),
    (
        ("bad.txt", "text/plain", b"content"),
        ("logo.png", "image/png", b"<script>alert(1)</script>"),
    ),
    ids=("non_image_extension", "non_image_content"),
)
def test_image_field_clean_rejects_non_image(filename, content_type, body):
    field = ImageField(required=False)
    payload = SimpleUploadedFile(filename, body, content_type=content_type)
    with pytest.raises(ValidationError):
        field.clean(payload)


def test_image_field_clean_accepts_valid_image(make_image):
    field = ImageField(required=False)
    valid_file = make_image("logo.png")
    assert field.clean(valid_file) == valid_file


def test_profile_picture_field_set_widget_data():
    field = ProfilePictureField(user="some_user", upload_only=True)
    field.set_widget_data()
    assert field.widget.user == "some_user"
    assert field.widget.upload_only is True


@pytest.mark.parametrize(
    ("kwargs", "data", "expected"),
    (
        ({"required": False}, "not a dict", None),
        ({"required": True, "current_picture": "existing"}, {"action": "keep"}, None),
        ({"required": False, "current_picture": None}, {"action": "keep"}, None),
        ({"required": False}, {"action": "remove"}, False),
        ({"required": False}, {"action": "unknown_action"}, None),
    ),
    ids=(
        "non_dict",
        "keep_with_current",
        "keep_not_required",
        "remove_not_required",
        "unknown_action",
    ),
)
def test_profile_picture_field_clean(kwargs, data, expected):
    assert ProfilePictureField(**kwargs).clean(data) is expected


@pytest.mark.parametrize(
    ("kwargs", "data", "code"),
    (
        ({"required": True, "current_picture": None}, {"action": "keep"}, "required"),
        ({"required": True}, {"action": "remove"}, "required"),
        ({"required": False}, {"action": "upload", "file": None}, "required"),
        ({"required": False, "upload_only": True}, {"action": "select_1"}, "invalid"),
        (
            {"required": False},
            {"action": "upload", "file": SimpleUploadedFile("test.txt", b"data")},
            "invalid",
        ),
        (
            {"required": False},
            {
                "action": "upload",
                "file": SimpleUploadedFile(
                    "avatar.html",
                    b"<script>alert(1)</script>",
                    content_type="image/png",
                ),
            },
            "invalid",
        ),
        (
            {"required": False},
            {
                "action": "upload",
                "file": SimpleUploadedFile(
                    "big.png",
                    b"x" * (settings.FILE_UPLOAD_DEFAULT_LIMIT + 1),
                    content_type="image/png",
                ),
            },
            "invalid",
        ),
        (
            {"required": False},
            {
                "action": "upload",
                "file": SimpleUploadedFile(
                    "avatar.png", b"x" * 100, content_type="image/png"
                ),
            },
            None,
        ),
    ),
    ids=(
        "keep_without_current_required",
        "remove_required",
        "upload_no_file",
        "select_when_upload_only",
        "upload_wrong_content_type",
        "upload_non_image_extension",
        "upload_oversized",
        "upload_non_image_content",
    ),
)
def test_profile_picture_field_clean_rejects(kwargs, data, code):
    with pytest.raises(ValidationError) as exc_info:
        ProfilePictureField(**kwargs).clean(data)
    assert exc_info.value.code == code


def test_profile_picture_field_clean_upload_valid_file(make_image):
    field = ProfilePictureField(required=False)
    valid_file = make_image("avatar.png")
    result = field.clean({"action": "upload", "file": valid_file})
    assert result == valid_file


def test_image_field_rejects_pixel_bomb(make_image, monkeypatch):
    monkeypatch.setattr(PIL.Image, "MAX_IMAGE_PIXELS", 99)
    field = ImageField(required=False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PIL.Image.DecompressionBombWarning)
        with pytest.raises(ValidationError) as exc_info:
            field.validate(make_image(width=10, height=10))
    assert "pixels" in str(exc_info.value)


def test_image_field_skips_stored_file(monkeypatch):
    calls = []
    monkeypatch.setattr("pretalx.common.forms.fields.validate_image", calls.append)
    field = ImageField(required=False)

    class StoredFieldFile:
        name = "logo.webp"

        def __bool__(self):
            return True

    field.validate(StoredFieldFile())
    assert calls == []


@pytest.mark.django_db
def test_profile_picture_field_clean_select_valid_picture():
    user = UserFactory()
    picture = ProfilePictureFactory(user=user)
    field = ProfilePictureField(required=False, user=user)

    result = field.clean({"action": f"select_{picture.pk}"})

    assert result == picture


@pytest.mark.django_db
@pytest.mark.parametrize(
    "make_pk_suffix",
    (
        lambda: "99999",
        lambda: "abc",
        lambda: ProfilePictureFactory(user=UserFactory()).pk,
    ),
    ids=("nonexistent", "non_numeric", "other_users_picture"),
)
def test_profile_picture_field_clean_select_invalid_pk(make_pk_suffix):
    user = UserFactory()
    field = ProfilePictureField(required=False, user=user)

    with pytest.raises(ValidationError) as exc_info:
        field.clean({"action": f"select_{make_pk_suffix()}"})
    assert exc_info.value.code == "invalid"


@pytest.mark.parametrize(
    ("data", "expected"),
    (
        ("not a dict", False),
        ({"action": "keep"}, False),
        ({"action": "remove"}, True),
        ({"action": "upload"}, True),
        ({"action": "select_1"}, True),
    ),
    ids=("non_dict", "keep", "remove", "upload", "select"),
)
def test_profile_picture_field_has_changed(data, expected):
    field = ProfilePictureField()
    assert field.has_changed(None, data) is expected


def test_profile_picture_field_disabled_ignores_submitted_data():
    field = ProfilePictureField(disabled=True)

    assert field.bound_data({"action": "remove", "file": None}, "current") == "current"


@pytest.mark.parametrize(
    ("tz", "value"),
    (("Europe/Berlin", "0001-01-01T00:00"), ("America/New_York", "9999-12-31T23:59")),
    ids=("before_utc_min", "after_utc_max"),
)
def test_datetime_field_rejects_value_outside_utc_range(tz, value):
    field = DateTimeField()

    with (
        timezone.override(zoneinfo.ZoneInfo(tz)),
        pytest.raises(ValidationError) as excinfo,
    ):
        field.clean(value)

    assert excinfo.value.code == "invalid"


@pytest.mark.parametrize(
    ("tz", "value", "expected_utc"),
    (
        (
            "Asia/Manila",
            "0001-01-01T00:00",
            dt.datetime(1, 1, 1, 15, 56, 8, tzinfo=dt.UTC),
        ),
        (
            "Europe/Berlin",
            "9999-12-31T23:59",
            dt.datetime(9999, 12, 31, 22, 59, tzinfo=dt.UTC),
        ),
    ),
    ids=("lmt_west_of_utc", "east_of_utc_at_max"),
)
def test_datetime_field_accepts_extreme_value_inside_utc_range(tz, value, expected_utc):
    field = DateTimeField()

    with timezone.override(zoneinfo.ZoneInfo(tz)):
        result = field.clean(value)

    assert result == expected_utc


@pytest.mark.parametrize(
    ("tz", "value", "expected"),
    (
        (
            "Asia/Manila",
            dt.datetime(2026, 2, 9, 23, 0, tzinfo=dt.UTC),
            dt.datetime(2026, 2, 10, 7, 0),
        ),
        (
            "America/New_York",
            dt.datetime(1, 1, 1, tzinfo=dt.UTC),
            dt.datetime(1, 1, 1, tzinfo=dt.UTC),
        ),
        (
            "Pacific/Kiritimati",
            dt.datetime(9999, 12, 31, 23, 59, tzinfo=dt.UTC),
            dt.datetime(9999, 12, 31, 23, 59, tzinfo=dt.UTC),
        ),
    ),
    ids=("in_range", "below_local_min", "above_local_max"),
)
def test_datetime_field_prepare_value_keeps_unconvertible_value(tz, value, expected):
    field = DateTimeField()

    with timezone.override(zoneinfo.ZoneInfo(tz)):
        result = field.prepare_value(value)

    assert result == expected
    assert result.tzinfo == expected.tzinfo


def test_datetime_field_allows_empty_when_not_required():
    field = DateTimeField(required=False)

    assert field.clean("") is None


@pytest.mark.parametrize("value", ("#ff0000", "#f00"), ids=("long", "short"))
def test_color_field_accepts_valid_hex(value):
    field = ColorField()
    assert field.clean(value) == value


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
    assert attrs["pattern"] == "#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})"


def test_honeypot_field_validate_rejects_only_true():
    field = HoneypotField()
    field.validate(False)
    with pytest.raises(ValidationError):
        field.validate(True)


@pytest.mark.django_db
def test_availabilities_field_init_with_event_sets_initial(event):
    room = RoomFactory(event=event)
    avail = AvailabilityFactory(
        event=event, room=room, start=event.datetime_from, end=event.datetime_to
    )
    field = AvailabilitiesField(event=event, instance=room)

    assert json.loads(field.initial) == {
        "availabilities": [avail.serialize()],
        "event": {
            "timezone": event.timezone,
            "date_from": str(event.date_from),
            "date_to": str(event.date_to),
        },
    }


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
def test_availabilities_field_get_event_context_with_event_and_resolution(event):
    field = AvailabilitiesField(event=event, resolution=15)
    assert field._get_event_context() == {
        "event": {
            "timezone": event.timezone,
            "date_from": str(event.date_from),
            "date_to": str(event.date_to),
        },
        "resolution": 15,
    }


@pytest.mark.django_db
def test_availabilities_field_get_event_context_room_constraints(event):
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    speaker_field = AvailabilitiesField(event=event, instance=speaker)
    room_field = AvailabilitiesField(event=event, instance=room)

    assert "constraints" not in speaker_field._get_event_context()

    AvailabilityFactory(
        event=event, room=room, start=event.datetime_from, end=event.datetime_to
    )

    assert speaker_field._get_event_context()["constraints"] == [
        {
            "start": event.datetime_from.astimezone(event.tz).isoformat(),
            "end": event.datetime_to.astimezone(event.tz).isoformat(),
        }
    ]
    assert "constraints" not in room_field._get_event_context()


@pytest.mark.django_db
def test_availabilities_field_prepare_value_adds_event_context(event):
    field = AvailabilitiesField(event=event)
    context = field._get_event_context()
    avails = [
        {
            "start": "2026-01-01T10:00:00+00:00",
            "end": "2026-01-01T12:00:00+00:00",
            "id": None,
            "allDay": False,
        }
    ]

    assert json.loads(field.prepare_value(json.dumps({"availabilities": []}))) == {
        "availabilities": [],
        **context,
    }
    assert json.loads(field.prepare_value(avails)) == {
        "availabilities": avails,
        **context,
    }
    assert json.loads(
        field.prepare_value(
            json.dumps({"availabilities": [], "event": {"timezone": "custom"}})
        )
    ) == {"availabilities": [], "event": {"timezone": "custom"}}


@pytest.mark.parametrize("value", (42, "not json{{{"), ids=("non_string", "bad_json"))
def test_availabilities_field_prepare_value_returns_unparseable_input(value):
    field = AvailabilitiesField(event=EventFactory.build())
    assert field.prepare_value(value) == value


def _at(event, day, hour):
    return dt.datetime.combine(day, dt.time(hour, 0), tzinfo=event.tz)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("build_value", "expected"),
    (
        (
            lambda e: json.dumps(
                {
                    "availabilities": [
                        {
                            "start": _at(e, e.date_from, 9).isoformat(),
                            "end": _at(e, e.date_from, 17).isoformat(),
                        }
                    ]
                }
            ),
            lambda e: [(_at(e, e.date_from, 9), _at(e, e.date_from, 17))],
        ),
        (
            lambda e: [
                {
                    "start": _at(e, e.date_from, 9).isoformat(),
                    "end": _at(e, e.date_from, 17).isoformat(),
                }
            ],
            lambda e: [(_at(e, e.date_from, 9), _at(e, e.date_from, 17))],
        ),
        (
            lambda e: {
                "availabilities": [
                    {
                        "start": _at(e, e.date_from, 9).isoformat(),
                        "end": _at(e, e.date_from, 17).isoformat(),
                        "id": 42,
                        "allDay": True,
                    }
                ]
            },
            lambda e: [(_at(e, e.date_from, 9), _at(e, e.date_from, 17))],
        ),
        (
            lambda e: json.dumps(
                {
                    "availabilities": [
                        {
                            "start": _at(
                                e, e.date_from - dt.timedelta(days=5), 9
                            ).isoformat(),
                            "end": _at(
                                e, e.date_to + dt.timedelta(days=5), 17
                            ).isoformat(),
                        }
                    ]
                }
            ),
            lambda e: [
                (_at(e, e.date_from, 0), _at(e, e.date_to + dt.timedelta(days=1), 0))
            ],
        ),
        (lambda e: "", lambda e: []),
    ),
    ids=("json_string", "list_input", "dict_strips_id_and_allday", "clamped", "empty"),
)
def test_availabilities_field_clean(event, build_value, expected):
    field = AvailabilitiesField(event=event, required=False)

    result = field.clean(build_value(event))

    assert all(isinstance(a, Availability) for a in result)
    assert [(a.start, a.end) for a in result] == expected(event)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("required", "value", "code"),
    (
        (True, "", "required"),
        (True, json.dumps({"availabilities": []}), "required_availability"),
        (False, "not valid json", "invalid_json"),
        (False, json.dumps([1, 2, 3]), "invalid_format"),
        (False, json.dumps({"availabilities": "not a list"}), "invalid_format"),
        (
            False,
            json.dumps({"availabilities": ["not a dict"]}),
            "invalid_availability_format",
        ),
        (
            False,
            json.dumps(
                {
                    "availabilities": [
                        {
                            "start": "2026-01-01T09:00:00+00:00",
                            "end": "2026-01-01T17:00:00+00:00",
                            "extra": "bad",
                        }
                    ]
                }
            ),
            "invalid_availability_format",
        ),
        (
            False,
            json.dumps(
                {"availabilities": [{"start": "not-a-date", "end": "also-not"}]}
            ),
            "invalid_date",
        ),
    ),
    ids=(
        "empty_required",
        "no_availabilities_required",
        "invalid_json",
        "non_dict_json",
        "availabilities_not_list",
        "availability_not_dict",
        "extra_keys",
        "invalid_date",
    ),
)
def test_availabilities_field_clean_rejects(event, required, value, code):
    field = AvailabilitiesField(event=event, required=required)
    with pytest.raises(ValidationError) as exc_info:
        field.clean(value)
    assert exc_info.value.code == code


@pytest.mark.django_db
def test_availabilities_field_parse_datetime_naive_gets_event_tz(event):
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


@pytest.mark.django_db
def test_profile_picture_field_save_applies_cleaned_value(make_image):
    speaker = SpeakerFactory()
    user = speaker.user
    first = ProfilePictureFactory(user=user)
    second = ProfilePictureFactory(user=user)
    field = ProfilePictureField()

    def stored_picture_id():
        return SpeakerProfile.objects.values_list("profile_picture_id", flat=True).get(
            pk=speaker.pk
        )

    field.save(instance=speaker, user=user, value=None)
    field.save(instance=speaker, user=user, value=False)
    assert stored_picture_id() is None

    field.save(instance=speaker, user=user, value=first)
    user.refresh_from_db(fields=["profile_picture"])
    assert stored_picture_id() == first.pk
    assert user.profile_picture_id == first.pk

    first_updated = first.updated
    field.save(instance=speaker, user=user, value=second)
    first.refresh_from_db()
    assert stored_picture_id() == second.pk
    assert first.updated > first_updated

    second_updated = second.updated
    field.save(instance=speaker, user=user, value=False)
    second.refresh_from_db()
    assert stored_picture_id() is None
    assert second.updated > second_updated

    field.save(instance=speaker, user=user, value=make_image("avatar.png"))
    assert stored_picture_id() not in (None, first.pk, second.pk)


@pytest.mark.django_db
def test_availabilities_field_validate_availability_with_datetime_objects(event):
    field = AvailabilitiesField(event=event, required=False)
    start = dt.datetime.combine(event.date_from, dt.time(9, 0), tzinfo=event.tz)
    end = dt.datetime.combine(event.date_from, dt.time(17, 0), tzinfo=event.tz)
    rawavail = {"start": start, "end": end}

    field._validate_availability(rawavail)

    assert rawavail["start"] == start
    assert rawavail["end"] == end


# --- MultiEmailField ---


def test_multi_email_field_uses_multi_email_input_widget():
    field = MultiEmailField()

    assert isinstance(field.widget, MultiEmailInput)


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ("a@example.com,b@example.com", ["a@example.com", "b@example.com"]),
        ("a@example.com\nb@example.com", ["a@example.com", "b@example.com"]),
        ("  a@example.com  ,  b@example.com  ", ["a@example.com", "b@example.com"]),
        ("Test@Example.COM", ["test@example.com"]),
        (
            "b@example.com,a@example.com,b@example.com",
            ["b@example.com", "a@example.com"],
        ),
        ("a@example.com,,\n,b@example.com", ["a@example.com", "b@example.com"]),
        ("", []),
    ),
    ids=("comma", "newline", "whitespace", "lowercases", "dedup", "blanks", "empty"),
)
def test_multi_email_field_clean(raw, expected):
    assert MultiEmailField(required=False).clean(raw) == expected


def test_multi_email_field_clean_invalid_lists_all_offending_tokens():
    field = MultiEmailField(required=False)

    with pytest.raises(ValidationError) as exc_info:
        field.clean("not-an-email,still-not-one,valid@example.com")

    message = str(exc_info.value)
    assert "not-an-email" in message
    assert "still-not-one" in message


@pytest.mark.parametrize(
    ("initial", "data", "expected"),
    (
        (["example.com", "sub.example.com"], "Example.COM, sub.example.com", False),
        (["example.com"], "example.com, other.example", True),
        ([], "", False),
        (None, "", False),
        # Invalid input is treated as changed so form validation surfaces
        # the error rather than silently no-op'ing.
        (["example.com"], "not_a_domain", True),
    ),
    ids=("normalised_equal", "extra_token", "both_empty", "none_initial", "invalid"),
)
def test_multi_token_field_has_changed(initial, data, expected):
    assert MultiDomainField(required=False).has_changed(initial, data) is expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ("example.com,sub.example.org", ["example.com", "sub.example.org"]),
        ("example.com sub.example.org", ["example.com", "sub.example.org"]),
        ("example.com\nsub.example.org", ["example.com", "sub.example.org"]),
        ("Example.COM", ["example.com"]),
        (
            "b.example.com,a.example.com,b.example.com",
            ["b.example.com", "a.example.com"],
        ),
        ("example.com,,\nsub.example.com,, ", ["example.com", "sub.example.com"]),
        ("", []),
    ),
    ids=("comma", "whitespace", "newline", "lowercases", "dedup", "blanks", "empty"),
)
def test_multi_domain_field_clean(raw, expected):
    assert MultiDomainField(required=False).clean(raw) == expected


def test_multi_domain_field_clean_invalid_raises():
    field = MultiDomainField(required=False)

    with pytest.raises(ValidationError, match="not_a_domain"):
        field.clean("example.com,not_a_domain")


def _css_field(current_text=""):
    field = CssField(required=False)
    field._current_text = current_text
    return field


_css_upload = SimpleUploadedFile("new.css", b"body { color: green; }")


@pytest.mark.parametrize(
    ("current_text", "data_list", "expected"),
    (
        ("body { color: red; }", [None, "body { color: red; }"], None),
        ("body {\n  color: red;\n}", [None, "body {\r\n  color: red;\r\n}\r\n"], None),
        (
            "body { color: red; }",
            [None, "body { color: blue; }"],
            b"body { color: blue; }",
        ),
        ("body { color: red; }", [None, ""], False),
        ("body { color: red; }", [False, "body { color: red; }"], False),
        (
            "body { color: red; }",
            [False, "body { color: blue; }"],
            b"body { color: blue; }",
        ),
        ("body { color: red; }", [False, ""], False),
        ("", [None, "body { color: blue; }"], b"body { color: blue; }"),
        ("", [], None),
        ("body { color: red; }", [_css_upload, "body { color: blue; }"], _css_upload),
    ),
    ids=(
        "untouched",
        "untouched_browser_crlf",
        "typed",
        "emptied",
        "cleared",
        "cleared_and_typed",
        "cleared_and_emptied",
        "typed_without_file",
        "nothing_at_all",
        "upload_wins_over_typed",
    ),
)
def test_css_field_compress(current_text, data_list, expected):
    value = _css_field(current_text).compress(data_list)

    if isinstance(expected, bytes):
        assert value.read() == expected
    else:
        assert value is expected


@pytest.mark.parametrize("value", (None, False), ids=("no_change", "removal"))
def test_css_field_validate_accepts(value):
    _css_field().validate(value)


@pytest.mark.parametrize("consumed", (False, True), ids=("fresh", "already_read"))
def test_css_field_validate_rejects_malicious_css(consumed):
    upload = SimpleUploadedFile("new.css", b"body { position: fixed; }")
    if consumed:
        upload.read()

    with pytest.raises(ValidationError, match="position"):
        _css_field().validate(upload)


def test_css_field_validate_leaves_the_file_readable():
    upload = SimpleUploadedFile("new.css", b"body { color: green; }")

    _css_field().validate(upload)

    assert upload.read() == b"body { color: green; }"


def test_css_field_has_changed():
    field = _css_field()
    current = SimpleUploadedFile("custom.css", b"body { color: red; }\n")

    assert field.has_changed(current, [None, "body { color: red; }\r\n"]) is False
    assert field.has_changed(current, [None, "body { color: blue; }"]) is True


def test_css_field_disabled_ignores_submitted_data():
    field = _css_field("body { color: red; }")
    field.disabled = True

    assert field.has_changed(None, [None, "body { color: blue; }"]) is False
    assert field.bound_data([None, "body { color: blue; }"], "current") == "current"


def test_css_field_validates_even_when_nothing_was_submitted():
    def reject(value):
        raise ValidationError("rejected")

    field = _css_field("body { color: red; }")
    field.validators = [reject]

    with pytest.raises(ValidationError, match="rejected"):
        field.clean([None, ""])
