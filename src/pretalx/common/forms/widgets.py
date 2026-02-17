# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
import json
from pathlib import Path

from django import forms
from django.core.files import File
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from i18nfield.forms import I18nTextarea
from django.db.models import Count
from django_scopes import scopes_disabled

from pretalx.common.text.phrases import phrases


def add_attribute(attrs, attr, css_class):
    attrs = attrs or {}
    class_str = (attrs.get(attr, "") or "").strip()
    class_str += " " + css_class
    attrs[attr] = class_str.strip()
    return attrs


class PasswordInput(forms.PasswordInput):
    css_class = "password-input"

    def _get_toggle_markup(self):
        show_password = _("Show password")
        hide_password = _("Hide password")
        return f"""<button type="button" class="password-toggle" aria-label="{show_password}" data-show-label="{show_password}" data-hide-label="{hide_password}">
                <i class="fa fa-eye" aria-hidden="true"></i>
            </button>"""

    def _get_extra_markup(self):
        return ""

    def _prepare_attrs(self):
        self.attrs = add_attribute(self.attrs, "class", self.css_class)

    def render(self, name, value, attrs=None, renderer=None):
        self._prepare_attrs()
        return mark_safe(
            super().render(name, value, self.attrs)
            + self._get_toggle_markup()
            + self._get_extra_markup()
        )

    class Media:
        js = [forms.Script("common/js/forms/password.js", defer="")]
        css = {"all": ["common/css/forms/password.css"]}


class PasswordStrengthInput(PasswordInput):
    css_class = "password_strength"

    def _get_extra_markup(self):
        message = _(
            'This password would take <em class="password_strength_time"></em> to crack.'
        )
        return f"""
        <div class="password-progress">
            <div class="password-progress-bar progress">
                <div class="progress-bar bg-warning password_strength_bar"
                     role="progressbar"
                     aria-valuenow="0"
                     aria-valuemin="0"
                     aria-valuemax="4">
                </div>
            </div>
            <small class="d-none password_strength_info form-text text-muted">
                {message}
            </small>
        </div>
        """

    def _prepare_attrs(self):
        super()._prepare_attrs()
        self.attrs["autocomplete"] = "new-password"

    class Media:
        js = [
            forms.Script("vendored/zxcvbn.js", defer=""),
            forms.Script("common/js/forms/password.js", defer=""),
        ]
        css = {"all": ["common/css/forms/password.css"]}


class PasswordConfirmationInput(PasswordInput):
    css_class = "password_confirmation"

    def __init__(self, confirm_with=None, attrs=None, render_value=False):
        super().__init__(attrs, render_value)
        self.confirm_with = confirm_with

    def _get_extra_markup(self):
        warning = _("Warning") + ":"
        content = _("Your passwords don’t match.")
        return f"""
        <small class="d-none password_strength_info form-text text-muted">
            <span class="label label-danger">{warning}</span>
            <span>{content}</span>
        </small>
        """

    def _prepare_attrs(self):
        super()._prepare_attrs()
        self.attrs["data-confirm-with"] = str(self.confirm_with)


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
            forms.Script("vendored/markdown-toolbar.js", defer=""),
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


class I18nMarkdownTextarea(I18nTextarea):
    widget = MarkdownWidget

    def format_output(self, rendered_widgets, id_):
        css_classes = "i18n-form-group i18n-markdown-group"
        if len(rendered_widgets) <= 1:
            css_classes += " i18n-form-single-language"
        return f'<div class="{css_classes}" id="{escape(id_)}">{"".join(rendered_widgets)}</div>'


class BiographyWidget(MarkdownWidget):
    template_name = "common/widgets/biography.html"

    def __init__(self, suggestions=None, attrs=None):
        super().__init__(attrs)
        self.suggestions = suggestions or []

    def get_context(self, name, value, attrs):
        from pretalx.common.templatetags.rich_text import (  # noqa: PLC0415
            render_markdown_plaintext,
        )

        ctx = super().get_context(name, value, attrs)
        suggestions = []
        biographies = {}
        for s in self.suggestions:
            profile_id = str(s["id"])
            plaintext = render_markdown_plaintext(s["biography"])
            preview = plaintext[:200] + ("…" if len(plaintext) > 200 else "")
            suggestions.append(
                {
                    "id": profile_id,
                    "event_name": s["event_name"],
                    "preview": preview,
                }
            )
            biographies[profile_id] = s["biography"]
        ctx["suggestions"] = suggestions
        ctx["biographies"] = biographies
        return ctx

    class Media:
        js = [
            forms.Script("vendored/choices/choices.min.js", defer=""),
            forms.Script("common/js/forms/select.js", defer=""),
            forms.Script("common/js/forms/biography_suggestions.js", defer=""),
        ]
        css = {
            "all": ["vendored/choices/choices.min.css", "common/css/forms/select.css"]
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
        ctx["widget"]["attrs"]["data-required-message"] = str(
            _("Please select an option.")
        )
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
        elif self.color_field and callable(self.color_field):
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


class MultiEmailInput(forms.TextInput):
    def __init__(self, attrs=None, delimiter=","):
        self.delimiter = delimiter
        attrs = add_attribute(attrs, "class", "tags-input")
        super().__init__(attrs=attrs)

    def format_value(self, value):
        if isinstance(value, (list, tuple)):
            return self.delimiter.join(value)
        return value or ""

    class Media:
        js = [
            forms.Script("vendored/choices/choices.min.js", defer=""),
            forms.Script("common/js/forms/multi-email.js", defer=""),
        ]
        css = {
            "all": ["vendored/choices/choices.min.css", "common/css/forms/select.css"]
        }


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


class ProfilePictureWidget(forms.Widget):
    template_name = "common/widgets/profile_picture.html"

    def __init__(self, user=None, current_picture=None, upload_only=False, attrs=None):
        super().__init__(attrs)
        self.user = user
        self.current_picture = current_picture
        self.upload_only = upload_only

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        widget_id = attrs.get("id", name) if attrs else name

        current = None
        if self.current_picture and self.current_picture.has_avatar:
            current = {
                "pk": self.current_picture.pk,
                "url": self.current_picture.avatar.url,
                "thumbnail_url": self.current_picture.get_avatar_url(
                    thumbnail="default"
                )
                or self.current_picture.avatar.url,
            }

        other_pictures = []
        if self.user and not self.upload_only:
            with scopes_disabled():
                # beware circular imports
                from pretalx.person.models import ProfilePicture  # noqa: PLC0415

                pictures = (
                    ProfilePicture.objects.filter(user=self.user)
                    .exclude(avatar="")
                    .exclude(avatar__isnull=True)
                    .annotate(event_count=Count("speakers__event", distinct=True))
                    .select_related("user")
                    .prefetch_related("speakers__event")
                    .order_by("-updated")
                )
                for pic in pictures:
                    is_current = (
                        self.current_picture and pic.pk == self.current_picture.pk
                    )
                    event_count = pic.event_count
                    if event_count == 1:
                        first_speaker = pic.speakers.first()
                        label = str(first_speaker.event.name) if first_speaker else ""
                    elif event_count > 1:
                        label = _("{count} events").format(count=event_count)
                    else:
                        label = ""
                    other_pictures.append(
                        {
                            "pk": pic.pk,
                            "url": pic.avatar.url,
                            "thumbnail_url": pic.get_avatar_url(thumbnail="default")
                            or pic.avatar.url,
                            "label": label,
                            "is_current": is_current,
                        }
                    )

        context["widget"].update(
            {
                "widget_id": widget_id,
                "current_picture": current,
                "other_pictures": other_pictures,
            }
        )
        return context

    def value_from_datadict(self, data, files, name):
        action = data.get(f"{name}_action", "keep")
        file = files.get(name)
        return {"action": action, "file": file}

    def use_required_attribute(self, initial):
        return False

    class Media:
        js = [
            forms.Script("vendored/cropper.min.js", defer=""),
            forms.Script("common/js/ui/dialog.js", defer=""),
            forms.Script("common/js/forms/profile_picture.js", defer=""),
        ]
        css = {
            "all": [
                "common/css/ui/dialog.css",
                "vendored/cropper.min.css",
                "common/css/forms/profile_picture.css",
            ]
        }


class HoneypotWidget(forms.CheckboxInput):
    """A hidden checkbox widget for honeypot spam protection.

    Renders as a visually hidden checkbox that is marked as required.
    Spam bots typically fill in all required fields, so if this is checked,
    we know it's a bot.
    """

    template_name = "common/widgets/honeypot.html"

    class Media:
        css = {"all": ["common/css/forms/honeypot.css"]}


class ToggleChoiceWidget(forms.Select):
    """A widget that renders a toggle button for binary choices.

    Displays a button showing the current selection, toggles between the two
    choices on click.
    """

    template_name = "common/widgets/toggle_choice.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        choices = list(self.choices)
        if len(choices) != 2:
            raise ValueError(
                f"ToggleChoiceWidget requires exactly 2 choices, got {len(choices)}"
            )

        choices_data = {
            str(choices[0][0]): str(choices[0][1]),
            str(choices[1][0]): str(choices[1][1]),
        }
        toggle_values = [str(choices[0][0]), str(choices[1][0])]
        current_value = str(value) if value else toggle_values[0]
        if current_value not in toggle_values:
            current_value = toggle_values[0]
        current_label = choices_data[current_value]
        current_index = toggle_values.index(current_value)

        context["widget"]["choices_json"] = json.dumps(choices_data)
        context["widget"]["values_json"] = json.dumps(toggle_values)
        context["widget"]["current_label"] = current_label
        context["widget"]["value"] = current_value
        context["widget"]["aria_pressed"] = "true" if current_index == 1 else "false"
        return context

    class Media:
        js = [forms.Script("common/js/forms/toggle_choice.js", defer="")]
