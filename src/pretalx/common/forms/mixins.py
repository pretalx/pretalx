# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import logging
import re
from functools import partial

from django import forms
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _
from hierarkey.forms import HierarkeyForm
from i18nfield.forms import I18nFormField, I18nFormMixin, I18nModelForm, I18nTextarea

from pretalx.common.forms.widgets import I18nMarkdownTextarea
from pretalx.submission.models.cfp import default_fields

logger = logging.getLogger(__name__)

WORD_REGEX = re.compile(r"\b\w+\b")


class ReadOnlyFlag:
    def __init__(self, *args, read_only=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.read_only = read_only
        if read_only:
            for field in self.fields.values():
                field.disabled = True

    def clean(self):
        if self.read_only:
            raise forms.ValidationError(_("You are trying to change read-only data."))
        return super().clean()


class RequestRequire:
    class Media:
        js = [forms.Script("common/js/forms/character-limit.js", defer="")]
        css = {"all": ["common/css/forms/character-limit.css"]}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        count_chars = self.event.cfp.settings["count_length_in"] == "chars"
        for key in self.Meta.request_require:
            visibility = self.event.cfp.fields.get(key, default_fields()[key])[
                "visibility"
            ]
            if visibility == "do_not_ask":
                self.fields.pop(key, None)
            elif field := self.fields.get(key):
                field.required = visibility == "required"
                min_value = self.event.cfp.fields.get(key, {}).get("min_length")
                max_value = self.event.cfp.fields.get(key, {}).get("max_length")
                if min_value or max_value:
                    if min_value and count_chars:
                        field.widget.attrs["data-minlength"] = min_value
                    if max_value and count_chars:
                        field.widget.attrs["data-maxlength"] = max_value
                    field.validators.append(
                        partial(
                            self.validate_field_length,
                            min_length=min_value,
                            max_length=max_value,
                            count_in=self.event.cfp.settings["count_length_in"],
                        )
                    )
                    field.original_help_text = getattr(field, "original_help_text", "")
                    field.added_help_text = self.get_help_text(
                        "",
                        min_value,
                        max_value,
                        self.event.cfp.settings["count_length_in"],
                    )
                    field.help_text = (
                        field.original_help_text + " " + field.added_help_text
                    )
        if field := self.fields.get("tags"):
            min_number, max_number = self.event.cfp.tag_limits
            field.original_help_text = getattr(
                field, "original_help_text", field.help_text or ""
            )
            if min_number or max_number:
                field.validators.append(
                    partial(
                        self.validate_tag_count,
                        min_number=min_number,
                        max_number=max_number,
                    )
                )
                field.added_help_text = self.get_tag_help_text(
                    "", min_number, max_number
                )
                field.help_text = (
                    field.original_help_text + " " + field.added_help_text
                ).strip()
            elif field.original_help_text:
                field.help_text = field.original_help_text

    @staticmethod
    def get_help_text(text, min_length, max_length, count_in="chars"):
        if not min_length and not max_length:
            return text
        text = str(text) + " " if text else ""
        texts = {
            "minmaxwords": _(
                "Please write between {min_length} and {max_length} words."
            ),
            "minmaxchars": _(
                "Please write between {min_length} and {max_length} characters."
            ),
            "minwords": _("Please write at least {min_length} words."),
            "minchars": _("Please write at least {min_length} characters."),
            "maxwords": _("Please write at most {max_length} words."),
            "maxchars": _("Please write at most {max_length} characters."),
        }
        length = ("min" if min_length else "") + ("max" if max_length else "")
        message = texts[length + count_in].format(
            min_length=min_length, max_length=max_length
        )
        return (text + str(message)).strip()

    @staticmethod
    def validate_field_length(value, min_length, max_length, count_in):
        if count_in == "chars":
            # Line breaks should only be counted as one character
            length = len(value.replace("\r\n", "\n"))
        else:
            length = len(re.findall(WORD_REGEX, value))
        if (min_length and min_length > length) or (max_length and max_length < length):
            error_message = RequestRequire.get_help_text(
                "", min_length, max_length, count_in
            )
            errors = {
                "chars": _("You wrote {count} characters."),
                "words": _("You wrote {count} words."),
            }
            error_message += " " + str(errors[count_in]).format(count=length)
            raise forms.ValidationError(error_message)

    @staticmethod
    def get_tag_help_text(text, min_number, max_number):
        if not min_number and not max_number:
            return text
        text = str(text) + " " if text else ""
        if min_number and max_number:
            if min_number == max_number:
                message = _("Please select exactly {count} tags.").format(
                    count=min_number
                )
            else:
                message = _("Please select between {min} and {max} tags.").format(
                    min=min_number, max=max_number
                )
        elif min_number:
            message = _("Please select at least {min} tags.").format(min=min_number)
        else:
            message = _("Please select at most {max} tags.").format(max=max_number)
        return (text + str(message)).strip()

    @staticmethod
    def validate_tag_count(value, min_number, max_number):
        count = len(value) if value else 0
        if (min_number and min_number > count) or (max_number and max_number < count):
            error_message = RequestRequire.get_tag_help_text("", min_number, max_number)
            error_message += " " + str(_("You selected {count} tags.")).format(
                count=count
            )
            raise forms.ValidationError(error_message)


class JsonSubfieldMixin:
    def __init__(self, *args, **kwargs):
        obj = kwargs.pop("obj", None)
        super().__init__(*args, **kwargs)
        if not getattr(self, "instance", None):
            if obj:
                self.instance = obj
            elif getattr(self, "obj", None):
                self.instance = self.obj
        for field, path in self.Meta.json_fields.items():
            data_dict = getattr(self.instance, path) or {}
            if field in data_dict:
                self.fields[field].initial = data_dict.get(field)
            else:
                defaults = self.instance._meta.get_field(path).default()
                self.fields[field].initial = defaults.get(field)

    def save(self, *args, **kwargs):
        if getattr(super(), "save", None):
            instance = super().save(*args, **kwargs)
        else:
            instance = self.instance
        for field, path in self.Meta.json_fields.items():
            # We don't need nested data for now
            data_dict = getattr(instance, path) or {}
            data_dict[field] = self.cleaned_data.get(field)
            setattr(instance, path, data_dict)
        if kwargs.get("commit", True):
            instance.save()
        return instance


class HierarkeyMixin:
    """This basically vendors hierarkey.forms.HierarkeyForm, but with more
    selective saving of fields.
    """

    BOOL_CHOICES = HierarkeyForm.BOOL_CHOICES

    def __init__(self, *args, obj, attribute_name="settings", **kwargs):
        self.obj = obj
        self.attribute_name = attribute_name
        self._s = getattr(obj, attribute_name)
        base_initial = self._s.freeze()
        base_initial.update(**kwargs["initial"])
        kwargs["initial"] = base_initial
        super().__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        """Saves all changed values to the database."""
        super().save(*args, **kwargs)
        for name in self.Meta.hierarkey_fields:
            field = self.fields.get(name)
            value = self.cleaned_data[name]
            if isinstance(value, UploadedFile):
                # Delete old file
                fname = self._s.get(name, as_type=File)
                if fname:
                    try:
                        default_storage.delete(fname.name)
                    except OSError:
                        logger.exception("Deleting file %s failed.", fname.name)

                # Create new file
                newname = default_storage.save(self.get_new_filename(value.name), value)
                value._name = newname  # noqa: SLF001 -- Django File internal
                self._s.set(name, value)
            elif isinstance(value, File):
                # file is unchanged
                continue
            elif not value and isinstance(field, forms.FileField):
                # file is deleted
                fname = self._s.get(name, as_type=File)
                if fname:
                    try:
                        default_storage.delete(fname.name)
                    except OSError:
                        logger.exception("Deleting file %s failed.", fname.name)
                del self._s[name]
            elif value is None:
                del self._s[name]
            elif self._s.get(name, as_type=type(value)) != value:
                self._s.set(name, value)

    def get_new_filename(self, name: str) -> str:
        nonce = get_random_string(length=8)
        suffix = name.rsplit(".", maxsplit=1)[-1]
        return f"{self.obj._meta.model_name}-{self.attribute_name}/{self.obj.pk}/{name}.{nonce}.{suffix}"


class PretalxI18nFormMixin(I18nFormMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field, I18nFormField):
                if type(field.widget) is I18nTextarea:
                    old = field.widget
                    field.widget = I18nMarkdownTextarea(
                        locales=old.locales, field=old.field, attrs=dict(old.attrs)
                    )
                    field.widget.enabled_locales = old.enabled_locales
                if not field.widget.attrs.get("placeholder"):
                    field.widget.attrs["placeholder"] = field.label

    class Media:
        css = {"all": ["orga/css/forms/i18n.css"]}


class PretalxI18nModelForm(PretalxI18nFormMixin, I18nModelForm):
    pass
