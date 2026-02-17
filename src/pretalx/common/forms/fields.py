# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.files.uploadedfile import UploadedFile
from django.forms import BooleanField, CharField, FileField, RegexField, ValidationError
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext_lazy as _
from django_scopes.forms import SafeModelChoiceField

from pretalx.common.forms.widgets import (
    AvailabilitiesWidget,
    ClearableBasenameFileInput,
    ColorPickerWidget,
    HoneypotWidget,
    ImageInput,
    PasswordConfirmationInput,
    PasswordStrengthInput,
    ProfilePictureWidget,
)
from pretalx.common.templatetags.filesize import filesize
from pretalx.person.models import ProfilePicture
from pretalx.schedule.models import Availability, Room

IMAGE_EXTENSIONS = {
    ".png": ["image/png", ".png"],
    ".jpg": ["image/jpeg", ".jpg"],
    ".jpeg": ["image/jpeg", ".jpeg"],
    ".gif": ["image/gif", ".gif"],
    ".svg": ["image/svg+xml", ".svg"],
    ".webp": ["image/webp", ".webp"],
}


class NewPasswordField(CharField):
    default_validators = [validate_password]

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", PasswordStrengthInput(render_value=False))
        super().__init__(*args, **kwargs)


class NewPasswordConfirmationField(CharField):
    def __init__(self, *args, **kwargs):
        confirm = kwargs.pop("confirm_with", None)
        kwargs.setdefault("widget", PasswordConfirmationInput(confirm_with=confirm))
        super().__init__(*args, **kwargs)


class SizeFileInput:
    """Takes the intended maximum upload size in bytes."""

    def __init__(self, *args, **kwargs):
        if "max_size" not in kwargs:  # Allow None, but only explicitly
            self.max_size = settings.FILE_UPLOAD_DEFAULT_LIMIT
        else:
            self.max_size = kwargs.pop("max_size")
        super().__init__(*args, **kwargs)
        self.size_warning = self.get_size_warning(self.max_size)
        self.original_help_text = (
            getattr(self, "original_help_text", "") or self.help_text
        )
        self.added_help_text = getattr(self, "added_help_text", "") + self.size_warning
        self.help_text = self.original_help_text + " " + self.added_help_text
        self.widget.attrs["data-maxsize"] = self.max_size
        self.widget.attrs["data-sizewarning"] = self.size_warning

    @staticmethod
    def get_size_warning(max_size=None, fallback=True):
        if not max_size and fallback:
            max_size = settings.FILE_UPLOAD_DEFAULT_LIMIT
        return _("Please do not upload files larger than {size}!").format(
            size=filesize(max_size)
        )

    def validate(self, value):
        super().validate(value)
        if (
            self.max_size
            and isinstance(value, UploadedFile)
            and value.size > self.max_size
        ):
            raise ValidationError(self.size_warning)


class ExtensionFileInput:
    widget = ClearableBasenameFileInput
    extensions = {}

    def __init__(self, *args, **kwargs):
        self.extensions = kwargs.pop("extensions", None) or self.extensions or {}
        super().__init__(*args, **kwargs)
        content_types = set()
        for ext in self.extensions.values():
            content_types.update(ext)
        content_types = ",".join(content_types)
        self.widget.attrs["accept"] = content_types

    def validate(self, value):
        super().validate(value)
        if value:
            filename = value.name
            extension = Path(filename).suffix.lower()
            if extension not in self.extensions:
                raise ValidationError(
                    _(
                        "This filetype ({extension}) is not allowed, it has to be one of the following: "
                    ).format(extension=extension)
                    + ", ".join(self.extensions.keys())
                )


class SizeFileField(SizeFileInput, FileField):
    pass


class ExtensionFileField(ExtensionFileInput, SizeFileField):
    pass


class ImageField(ExtensionFileField):
    widget = ImageInput
    extensions = IMAGE_EXTENSIONS


class ProfilePictureField(FileField):
    widget = ProfilePictureWidget

    ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    MAX_SIZE = settings.FILE_UPLOAD_DEFAULT_LIMIT

    def __init__(
        self,
        *args,
        user=None,
        current_picture=None,
        require_picture=False,
        upload_only=False,
        **kwargs,
    ):
        self.user = user
        self.current_picture = current_picture
        self.require_picture = require_picture
        self.upload_only = upload_only
        kwargs.setdefault("required", False)
        kwargs.setdefault("label", _("Profile picture"))
        super().__init__(*args, **kwargs)
        self.widget.user = user
        self.widget.current_picture = current_picture
        self.widget.upload_only = upload_only

    def clean(self, value, initial=None):
        if not isinstance(value, dict):
            return None

        action = value.get("action", "keep")
        file = value.get("file")

        if action == "keep":
            if self.require_picture and not self.current_picture:
                raise ValidationError(
                    _("Please provide a profile picture!"),
                    code="required",
                )
            self._cleaned_value = None
            return None

        if action == "remove":
            if self.require_picture:
                raise ValidationError(
                    _("Please provide a profile picture!"),
                    code="required",
                )
            self._cleaned_value = False
            return False

        if action.startswith("select_"):
            if self.upload_only:
                raise ValidationError(_("Invalid picture selection."), code="invalid")
            pk_str = action[len("select_") :]
            try:
                pk = int(pk_str)
            except (ValueError, TypeError):
                raise ValidationError(
                    _("Invalid picture selection."), code="invalid"
                ) from None
            from pretalx.person.models import ProfilePicture  # noqa: PLC0415

            try:
                picture = ProfilePicture.objects.get(pk=pk, user=self.user)
            except ProfilePicture.DoesNotExist:
                raise ValidationError(
                    _("Invalid picture selection."), code="invalid"
                ) from None
            self._cleaned_value = picture
            return picture

        if action == "upload":
            if not file:
                raise ValidationError(_("No file was uploaded."), code="required")
            if file.content_type not in self.ALLOWED_TYPES:
                raise ValidationError(
                    _("Please upload an image file (JPG, PNG, GIF, or WebP)."),
                    code="invalid",
                )
            if file.size > self.MAX_SIZE:
                raise ValidationError(
                    _("Please do not upload files larger than {size}!").format(
                        size="10 MB"
                    ),
                    code="invalid",
                )
            self._cleaned_value = file
            return file

    def has_changed(self, initial, data):
        if not isinstance(data, dict):
            return False
        return data.get("action", "keep") != "keep"

    def save(self, instance, user):
        value = getattr(self, "_cleaned_value", None)
        if value is None:
            return

        if isinstance(value, UploadedFile):
            instance.set_avatar(value)
            return

        old_picture = instance.profile_picture
        new_picture = None

        if value is False:
            new_picture = None
        elif isinstance(value, ProfilePicture):
            new_picture = value

        if new_picture != old_picture:
            instance.profile_picture = new_picture
            instance.save(update_fields=["profile_picture"])
            if old_picture:
                # Update old picture to bump its last modified timestamp,
                # so we can figure out when to clean it up.
                old_picture.save(update_fields=["updated"])
            if new_picture and not user.profile_picture:
                user.profile_picture = new_picture
                user.save(update_fields=["profile_picture"])


class ColorField(RegexField):
    regex = "^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$"
    max_length = 7
    widget = ColorPickerWidget

    def __init__(self, *args, **kwargs):
        super().__init__(*args, regex=self.regex, **kwargs)

    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget)
        attrs["pattern"] = self.regex[1:-1]
        return attrs


class SubmissionTypeField(SafeModelChoiceField):
    """Only include duration in a submission type’s representation
    if the duration is not a required CfP field (in which case, showing
    the default duration would be misleading, as it’s never used)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # All shown submission types in a form should belong to one event,
        # particularly in the non-organiser area where this field is used,
        # so we can just cache the rendering decision between instances.
        self.show_duration = None

    def label_from_instance(self, obj):
        if self.show_duration is None:
            self.show_duration = not bool(obj.event.cfp.require_duration)
        if self.show_duration:
            return str(obj)
        return str(obj.name)


class HoneypotField(BooleanField):
    """A honeypot field for spam protection.

    This field renders as a visually hidden checkbox. It should be added to
    forms that are publicly accessible and susceptible to spam. The form
    should use novalidate to prevent browser validation.

    Validation: If the field is checked (True), it's a spam bot, so raise
    a validation error. Legitimate users never see or interact with this field.
    """

    widget = HoneypotWidget

    def __init__(self, *args, **kwargs):
        # We manually render the required flag in the widget,
        # so we unset it here to bypass Django validation
        kwargs["required"] = False
        kwargs.setdefault("label", "")
        super().__init__(*args, **kwargs)

    def validate(self, value):
        if value:
            raise ValidationError(
                _("Form submission failed."),
                code="invalid",
            )


class AvailabilitiesField(CharField):
    widget = AvailabilitiesWidget
    default_error_messages = {
        "invalid_json": _("Submitted availabilities are not valid json: %(error)s."),
        "invalid_format": _(
            "Availability JSON does not comply with expected format: %(detail)s"
        ),
        "invalid_availability_format": _(
            "The submitted availability does not comply with the required format."
        ),
        "invalid_date": _("The submitted availability contains an invalid date."),
        "required_availability": _("Please fill in your availability!"),
    }

    def __init__(self, *args, event=None, instance=None, resolution=None, **kwargs):
        self.event = event
        self.instance = instance
        self.resolution = resolution

        if "initial" not in kwargs and self.instance and self.event:
            kwargs["initial"] = self._serialize(self.event, self.instance)

        super().__init__(*args, **kwargs)

    def set_initial_from_instance(self):
        if self.event and not self.initial:
            self.initial = self._serialize(self.event, self.instance)

    def _get_event_context(self):
        if not self.event:
            return {}
        result = {
            "event": {
                "timezone": self.event.timezone,
                "date_from": str(self.event.date_from),
                "date_to": str(self.event.date_to),
            },
        }
        if self.resolution:
            result["resolution"] = self.resolution
        if self.instance and not isinstance(self.instance, Room):
            room_avails = self.event.valid_availabilities.filter(room__isnull=False)
            if room_avails:
                merged_avails = Availability.union(room_avails)
                result["constraints"] = [
                    {
                        "start": avail.start.astimezone(self.event.tz).isoformat(),
                        "end": avail.end.astimezone(self.event.tz).isoformat(),
                    }
                    for avail in merged_avails
                ]
        return result

    def _serialize(self, event, instance):
        availabilities = []
        if instance and instance.pk:
            availabilities = [av.serialize() for av in instance.availabilities.all()]

        result = {
            "availabilities": [
                avail for avail in availabilities if avail["end"] > avail["start"]
            ],
        }
        result.update(self._get_event_context())
        return json.dumps(result)

    def prepare_value(self, value):
        if isinstance(value, str) and self.event:
            try:
                data = json.loads(value)
            except (ValueError, TypeError):
                return value
            if isinstance(data, dict) and "event" not in data:
                data.update(self._get_event_context())
                return json.dumps(data)
        return value

    def _parse_availabilities_json(self, jsonavailabilities):
        try:
            rawdata = json.loads(jsonavailabilities)
        except ValueError as e:
            raise ValidationError(
                self.error_messages["invalid_json"],
                code="invalid_json",
                params={"error": e},
            ) from None
        if not isinstance(rawdata, dict):
            raise ValidationError(
                self.error_messages["invalid_format"],
                code="invalid_format",
                params={"detail": f"Should be object, but is {type(rawdata)}"},
            )
        availabilities = rawdata.get("availabilities")
        if not isinstance(availabilities, list):
            raise ValidationError(
                self.error_messages["invalid_format"],
                code="invalid_format",
                params={
                    "detail": f"`availabilities` should be a list, but is {type(availabilities)}"
                },
            )
        return availabilities

    def _parse_datetime(self, strdate):
        obj = parse_datetime(strdate)
        if not obj:
            raise TypeError
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=self.event.tz)
        return obj

    def _validate_availability(self, rawavail):
        if not isinstance(rawavail, dict):
            raise ValidationError(
                self.error_messages["invalid_availability_format"],
                code="invalid_availability_format",
            )
        rawavail.pop("id", None)
        rawavail.pop("allDay", None)
        if set(rawavail.keys()) != {"start", "end"}:
            raise ValidationError(
                self.error_messages["invalid_availability_format"],
                code="invalid_availability_format",
            )

        try:
            for key in ("start", "end"):
                raw_value = rawavail[key]
                if not isinstance(raw_value, dt.datetime):
                    rawavail[key] = self._parse_datetime(raw_value)
        except (TypeError, ValueError):
            raise ValidationError(
                self.error_messages["invalid_date"], code="invalid_date"
            ) from None

        timeframe_start = dt.datetime.combine(
            self.event.date_from, dt.time(), tzinfo=self.event.tz
        )
        rawavail["start"] = max(rawavail["start"], timeframe_start)

        timeframe_end = dt.datetime.combine(
            self.event.date_to, dt.time(), tzinfo=self.event.tz
        )
        timeframe_end = timeframe_end + dt.timedelta(days=1)
        rawavail["end"] = min(rawavail["end"], timeframe_end)

    def clean(self, value):
        if isinstance(value, list):
            value = {"availabilities": value}
        if isinstance(value, dict):
            value = json.dumps(value)
        value = super().clean(value)
        if not value:
            if self.required:
                raise ValidationError(
                    self.error_messages["required_availability"],
                    code="required_availability",
                )
            return []

        rawavailabilities = self._parse_availabilities_json(value)
        availabilities = []

        for rawavail in rawavailabilities:
            self._validate_availability(rawavail)
            availabilities.append(Availability(event_id=self.event.id, **rawavail))

        if not availabilities and self.required:
            raise ValidationError(
                self.error_messages["required_availability"],
                code="required_availability",
            )

        return Availability.union(availabilities)
