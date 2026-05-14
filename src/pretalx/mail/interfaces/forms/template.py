# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from collections import defaultdict

from django.utils.functional import cached_property
from django.utils.html import escape

from pretalx.common.forms.mixins import PretalxI18nModelForm, ReadOnlyFlag
from pretalx.common.forms.widgets import MultiEmailInput
from pretalx.mail.domain.placeholders import placeholders_for_template
from pretalx.mail.models import MailTemplate
from pretalx.mail.validators import validate_text_placeholders


class MailTemplateForm(ReadOnlyFlag, PretalxI18nModelForm):
    def __init__(self, *args, **kwargs):
        # ``event`` is required, accepted either as a kwarg (direct use) or via
        # a pre-set attribute. The attribute path is for ``WriteSessionMailForm``,
        # whose diamond inheritance has ``SubmissionFilterForm`` consume the
        # ``event`` kwarg before this ``__init__`` runs.
        event = kwargs.pop("event", None) or getattr(self, "event", None)
        if event is None:
            raise TypeError("MailTemplateForm requires `event`")
        self.event = event
        kwargs["locales"] = event.locales
        super().__init__(*args, **kwargs)
        if not self.instance.event_id:
            self.instance.event = event
        self.fields["subject"].required = True
        self.fields["text"].required = True

    def get_valid_placeholders(self, **kwargs):
        return placeholders_for_template(self.instance)

    @cached_property
    def valid_placeholders(self):
        return self.get_valid_placeholders()

    @cached_property
    def grouped_placeholders(self):
        placeholders = self.get_valid_placeholders(ignore_data=True)
        grouped = defaultdict(list)
        specificity = ["slot", "submission", "user", "event", "other"]
        for placeholder in placeholders.values():
            if not placeholder.is_visible:
                continue
            placeholder.rendered_sample = escape(placeholder.render_sample(self.event))
            for arg in specificity:
                if arg in placeholder.required_context:
                    grouped[arg].append(placeholder)
                    break
            else:
                grouped["other"].append(placeholder)
        return grouped

    def clean_subject(self):
        text = self.cleaned_data["subject"]
        validate_text_placeholders(text, self.valid_placeholders)
        return text

    def clean_text(self):
        text = self.cleaned_data["text"]
        validate_text_placeholders(text, self.valid_placeholders)
        return text

    class Media:
        css = {"all": ["orga/css/forms/email.css"]}

    class Meta:
        model = MailTemplate
        fields = ["subject", "text", "reply_to", "bcc"]
        widgets = {"bcc": MultiEmailInput, "reply_to": MultiEmailInput}
