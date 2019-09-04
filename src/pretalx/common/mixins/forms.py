from functools import partial

from django import forms
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _

from pretalx.common.forms.utils import get_help_text, validate_field_length
from pretalx.common.phrases import phrases


class ReadOnlyFlag:
    def __init__(self, *args, read_only=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.read_only = read_only
        if read_only:
            for field in self.fields.values():
                field.disabled = True

    def clean(self):
        if self.read_only:
            raise forms.ValidationError(_('You are trying to change read only data.'))
        return super().clean()


class PublicContent:

    public_fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.Meta.public_fields:
            field = self.fields.get(field_name)
            if field:
                field.help_text = (field.help_text or '') + ' ' + str(phrases.base.public_content)


class MarkdownHelp:
    """Add 'You can use Markdown' phrase with a link to the documentation to the help text."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.Meta.markdown_fields:
            field = self.fields.get(field_name)
            if field:
                field.help_text = (field.help_text or '') + ' ' + str(phrases.base.use_markdown)


class CustomiseHelpText:
    """Replace help_text provided by the model class by one customisable by the organiser."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Insert customised help texts set by the organiser in front of generic help text like "you can use Markdown"
        for key in self.Meta.customise_help_fields:
            field = self.fields.get(key)
            if not field:
                continue
            help_text_key = 'help_text_' + key
            if help_text_key in self.event.cfp.__dict__.keys():
                field = self.fields[key]
                field.help_text = escape(str(self.event.cfp.__dict__[help_text_key]))


class RequestRequire:
    """Add minimal and maximal length of a form field to the help text."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        count_chars = self.event.settings.cfp_count_length_in == 'chars'
        for key in self.Meta.request_require:
            request = self.event.settings.get(f'cfp_request_{key}')
            require = self.event.settings.get(f'cfp_require_{key}')
            if not request:
                self.fields.pop(key)
            else:
                field = self.fields[key]
                field.required = require
                min_value = self.event.settings.get(f'cfp_{key}_min_length')
                max_value = self.event.settings.get(f'cfp_{key}_max_length')
                if min_value or max_value:
                    if min_value and count_chars:
                        field.widget.attrs[f'minlength'] = min_value
                    if max_value and count_chars:
                        field.widget.attrs[f'maxlength'] = max_value
                    field.validators.append(
                        partial(
                            validate_field_length,
                            min_length=min_value,
                            max_length=max_value,
                            count_in=self.event.settings.cfp_count_length_in,
                        )
                    )
                    field.help_text = get_help_text(
                        self.fields[key].help_text,
                        min_value,
                        max_value,
                        self.event.settings.cfp_count_length_in,
                    )
