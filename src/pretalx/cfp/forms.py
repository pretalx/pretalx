# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import re
from functools import partial

from django import forms
from django.utils.translation import gettext_lazy as _

from pretalx.common.templatetags.rich_text import rich_text
from pretalx.submission.models.cfp import default_fields

WORD_REGEX = re.compile(r"\b\w+\b")


class CfPFormMixin:
    """All forms used in the CfP step process should use this mixin.

    It serves to make it work with the CfP Flow editor, e.g. by allowing
    users to change help_text attributes of fields and reorder fields.
    Needs to go first before all other forms changing help_text behaviour.
    """

    def __init__(self, *args, field_configuration=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.field_configuration = field_configuration
        if self.field_configuration:
            field_order = [field_data["key"] for field_data in self.field_configuration]
            self.field_configuration = {
                field_data["key"]: field_data for field_data in field_configuration
            }
            for field_data in self.field_configuration:
                if field_data in self.fields:
                    self._update_cfp_texts(field_data)
            self._reorder_fields(field_order)

    def _reorder_fields(self, field_order):
        new_fields = {}
        for key in field_order:
            if key in self.fields:
                new_fields[key] = self.fields[key]
        # Add any remaining fields not in the config
        for key, field in self.fields.items():
            if key not in new_fields:
                new_fields[key] = field

        self.fields = new_fields

    def _update_cfp_texts(self, field_name):
        field = self.fields.get(field_name)
        if not field or not self.field_configuration:
            return
        field_data = self.field_configuration.get(field_name) or {}
        field.original_help_text = field_data.get("help_text") or ""
        if field.original_help_text:
            field.help_text = rich_text(
                str(field.original_help_text)
                + " "
                + str(getattr(field, "added_help_text", ""))
            )
        if field_data.get("label"):
            field.label = field_data["label"]


class RequestRequire:
    """Apply the event's CfP field configuration (visibility, min/max length,
    tag limits) to a form. Used by both speaker-facing and orga-facing
    forms — wherever CfP-controlled fields appear, the same rules apply.
    """

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
