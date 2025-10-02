from pathlib import Path

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.files.uploadedfile import UploadedFile
from django.forms import CharField, FileField, RegexField, ValidationError
from django.utils.translation import gettext_lazy as _
from django_scopes.forms import SafeModelChoiceField

from pretalx.common.forms.widgets import (
    ClearableBasenameFileInput,
    ColorPickerWidget,
    ImageInput,
    PasswordConfirmationInput,
    PasswordStrengthInput,
)
from pretalx.common.templatetags.filesize import filesize

IMAGE_EXTENSIONS = {
    ".png": ["image/png", ".png"],
    ".jpg": ["image/jpeg", ".jpg"],
    ".jpeg": ["image/jpeg", ".jpeg"],
    ".gif": ["image/gif", ".gif"],
    ".svg": ["image/svg+xml", ".svg"],
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
            if extension not in self.extensions.keys():
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
        # particularly in the non-organizer area where this field is used,
        # so we can just cache the rendering decision between instances.
        self.show_duration = None

    def label_from_instance(self, obj):
        if self.show_duration is None:
            self.show_duration = not bool(obj.event.cfp.require_duration)
        if self.show_duration:
            return str(obj)
        return str(obj.name)
