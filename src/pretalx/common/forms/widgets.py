# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
from pathlib import Path

from django import forms
from django.core.files import File
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from pretalx.common.text.phrases import phrases


def add_attribute(attrs, attr, css_class):
    attrs = attrs or {}
    class_str = (attrs.get(attr, "") or "").strip()
    class_str += " " + css_class
    attrs[attr] = class_str.strip()
    return attrs


class PasswordStrengthInput(forms.PasswordInput):
    def render(self, name, value, attrs=None, renderer=None):
        message = _(
            'This password would take <em class="password_strength_time"></em> to crack.'
        )
        markup = f"""
        <div class="password-progress">
            <div class="password-progress-bar progress">
                <div class="progress-bar bg-warning password_strength_bar"
                     role="progressbar"
                     aria-valuenow="0"
                     aria-valuemin="0"
                     aria-valuemax="4">
                </div>
            </div>
            <p class="text-muted password_strength_info d-none">
                <span style="margin-left:5px;">
                    {message}
                </span>
            </p>
        </div>
        """

        self.attrs = add_attribute(self.attrs, "class", "password_strength")
        self.attrs["autocomplete"] = "new-password"
        return mark_safe(super().render(name, value, self.attrs) + markup)

    class Media:
        js = [
            forms.Script("vendored/zxcvbn.js", defer=""),
            forms.Script("common/js/forms/password.js", defer=""),
        ]
        css = {"all": ["common/css/forms/password.css"]}


class PasswordConfirmationInput(forms.PasswordInput):
    def __init__(self, confirm_with=None, attrs=None, render_value=False):
        super().__init__(attrs, render_value)
        self.confirm_with = confirm_with

    def render(self, name, value, attrs=None, renderer=None):
        self.attrs["data-confirm-with"] = str(self.confirm_with)
        warning = _("Warning")
        content = _("Your passwords don’t match.")

        markup = f"""
        <div class="d-none password_strength_info">
            <p class="text-muted">
                <span class="label label-danger">{warning}</span>
                <span>{content}</span>
            </p>
        </div>
        """

        self.attrs = add_attribute(self.attrs, "class", "password_confirmation")
        return mark_safe(super().render(name, value, self.attrs) + markup)


class ClearableBasenameFileInput(forms.ClearableFileInput):
    class FakeFile(File):
        def __init__(self, file):
            self.file = file

        @property
        def name(self):
            return self.file.name

        def __str__(self):
            return Path(self.name).stem

        @property
        def url(self):
            return self.file.url

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx["widget"]["value"] = self.FakeFile(value)
        return ctx

    class Media:
        js = [forms.Script("common/js/forms/filesize.js", defer="")]


class ImageInput(ClearableBasenameFileInput):
    template_name = "common/widgets/image_input.html"

    class Media:
        css = {"all": ["common/css/forms/image.css"]}


class MarkdownWidget(forms.Textarea):
    template_name = "common/widgets/markdown.html"

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx["preview_help"] = phrases.base.use_markdown
        return ctx

    class Media:
        js = [
            forms.Script("vendored/marked.min.js", defer=""),
            forms.Script("vendored/purify.min.js", defer=""),
            forms.Script("common/js/ui/tabs.js", defer=""),
            forms.Script("common/js/forms/markdown.js", defer=""),
            forms.Script("common/js/forms/character-limit.js", defer=""),
        ]
        css = {
            "all": [
                "common/css/ui/tabs.css",
                "common/css/forms/markdown.css",
                "common/css/forms/character-limit.css",
            ]
        }


class EnhancedSelectMixin(forms.Select):
    # - add the "class: enhanced" attribute to the select widget
    # - if `description_field` is set, set data-description on options
    # - if `color_field` is set, set data-color on options
    def __init__(
        self, attrs=None, choices=(), description_field=None, color_field=None
    ):
        self.description_field = description_field
        self.color_field = color_field
        super().__init__(attrs, choices)

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx["widget"]["attrs"] = add_attribute(
            ctx["widget"]["attrs"], "class", "enhanced"
        )
        ctx["widget"]["attrs"]["tabindex"] = "-1"
        return ctx

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected, index, subindex, attrs
        )
        if value and getattr(value, "instance", None):
            if self.description_field and (
                description := getattr(value.instance, self.description_field, None)
            ):
                option["attrs"]["data-description"] = description
            if self.color_field and (
                color := getattr(value.instance, self.color_field, None)
            ):
                option["attrs"]["data-color"] = color
        else:
            if self.color_field and callable(self.color_field):
                option["attrs"]["data-color"] = self.color_field(value)
        return option

    class Media:
        js = [
            forms.Script("vendored/choices/choices.min.js", defer=""),
            forms.Script("common/js/forms/select.js", defer=""),
        ]
        css = {
            "all": ["vendored/choices/choices.min.css", "common/css/forms/select.css"]
        }


class EnhancedSelect(EnhancedSelectMixin, forms.Select):
    pass


class EnhancedSelectMultiple(EnhancedSelectMixin, forms.SelectMultiple):
    pass


def get_count(value, label):
    instance = getattr(value, "instance", None)
    if instance and hasattr(instance, "count"):
        return instance.count
    count = getattr(label, "count", 0)
    if callable(count):
        return count(label)
    return count


class SelectMultipleWithCount(EnhancedSelectMultiple):
    """A widget for multi-selects that correspond to countable values.

    This widget doesn't support some of the options of the default
    SelectMultiple, most notably it doesn't support optgroups. In
    return, it takes a third value per choice, makes zero-values
    disabled and sorts options by numerical value.
    """

    def optgroups(self, name, value, attrs=None):
        choices = sorted(
            self.choices, key=lambda choice: get_count(*choice), reverse=True
        )
        result = []
        for index, (option_value, label) in enumerate(choices):
            count = get_count(option_value, label)
            if count == 0:
                continue
            selected = str(option_value) in value
            result.append(
                self.create_option(
                    name,
                    value=option_value,
                    label=label,
                    selected=selected,
                    index=index,
                    count=count,
                )
            )
        return [(None, result, 0)]

    def create_option(self, name, value, label, *args, count=0, **kwargs):
        label = f"{label} ({count})"
        return super().create_option(name, value, label, *args, **kwargs)


class SearchInput(forms.TextInput):
    input_type = "search"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["attrs"]["placeholder"] = _("Search")
        return context


class TextInputWithAddon(forms.TextInput):
    template_name = "common/widgets/text_input_with_addon.html"

    def __init__(self, attrs=None, addon_before=None, addon_after=None):
        super().__init__(attrs)
        self.addon_before = addon_before
        self.addon_after = addon_after

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["addon_before"] = self.addon_before
        context["widget"]["addon_after"] = self.addon_after
        return context


class HtmlDateInput(forms.DateInput):
    input_type = "date"

    def format_value(self, value):
        if value and isinstance(value, (dt.date, dt.datetime)):
            return value.strftime("%Y-%m-%d")
        return value

    class Media:
        js = [forms.Script("common/js/forms/datefield.js", defer="")]


class HtmlDateTimeInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def format_value(self, value):
        if value and isinstance(value, dt.datetime):
            return value.strftime("%Y-%m-%dT%H:%M")
        return value

    class Media:
        js = [forms.Script("common/js/forms/datefield.js", defer="")]


class HtmlTimeInput(forms.TimeInput):
    input_type = "time"

    def format_value(self, value):
        if value and isinstance(value, (dt.time, dt.datetime)):
            return value.strftime("%H:%M")
        return value

    class Meta:
        js = [forms.Script("common/js/forms/datefield.js", defer="")]


class ColorPickerWidget(forms.TextInput):

    def __init__(self, attrs=None):
        attrs = add_attribute(attrs, "class", "colorpicker")
        super().__init__(attrs=attrs)

    class Media:
        js = [
            forms.Script("vendored/vanilla-picker.min.js", defer=""),
            forms.Script("orga/js/ui/colorpicker.js", defer=""),
        ]
        css = {"all": ["orga/css/forms/colorpicker.css"]}


class AvailabilitiesWidget(forms.TextInput):

    def __init__(self, attrs=None):
        attrs = add_attribute(attrs, "class", "availabilities-editor-data")
        super().__init__(attrs=attrs)

    class Media:
        js = [
            forms.Script("vendored/luxon.min.js", defer=""),
            forms.Script("vendored/fullcalendar/fullcalendar.min.js", defer=""),
            forms.Script("vendored/fullcalendar/luxon-plugin.min.js", defer=""),
            forms.Script("common/js/forms/availabilities.js", defer=""),
        ]
        css = {"all": ["common/css/forms/availabilities.css"]}


class AvatarCropWidget(ClearableBasenameFileInput):
    template_name = "common/widgets/avatar_crop_input.html"

    class Media:
        css = {
            "all": [
                "vendored/cropper.min.css",
                "common/css/forms/avatar_crop.css",
                "common/css/forms/image.css",
            ]
        }
        js = [
            forms.Script("vendored/cropper.min.js", defer=""),
            forms.Script("common/js/forms/avatar_crop.js", defer=""),
            forms.Script("common/js/forms/filesize.js", defer=""),
        ]
