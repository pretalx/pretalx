# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: AthinaDavari

from django import forms
from django.utils.translation import gettext_lazy as _
from i18nfield.forms import I18nFormField, I18nTextarea, I18nTextInput

from pretalx.common.forms.mixins import (
    JsonSubfieldMixin,
    PretalxI18nFormMixin,
    PretalxI18nModelForm,
    ReadOnlyFlag,
)
from pretalx.submission.models.cfp import CfP


class CfPSettingsForm(
    ReadOnlyFlag, PretalxI18nFormMixin, JsonSubfieldMixin, forms.Form
):
    mail_on_new_submission = forms.BooleanField(
        label=_("Send email on new proposal"),
        help_text=_(
            "If this setting is checked, you will receive an email to the organiser address for every received proposal."
        ),
        required=False,
    )
    submission_public_review = forms.BooleanField(
        label=_("Allow submitters to share their proposal publicly"),
        help_text=_(
            "Allow submitters to share a secret link to their proposal with others."
        ),
        required=False,
    )
    speakers_can_edit_submissions = forms.BooleanField(
        label=_("Allow speakers to edit their proposals and profiles"), required=False
    )

    def __init__(self, *args, obj, **kwargs):
        self.instance = obj
        super().__init__(*args, **kwargs)

        review_phase_link = f'<a href="{obj.orga_urls.review_settings}#tab-phases">{_("Review settings")}</a>'
        self.fields["speakers_can_edit_submissions"].help_text = _(
            "If disabled, speakers cannot edit their proposals regardless of the proposal state. "
            "This setting overrides the {review_phase_link} for speaker editing."
        ).format(review_phase_link=review_phase_link)
        if getattr(obj, "email", None):
            self.fields[
                "mail_on_new_submission"
            ].help_text += f' (<a href="mailto:{obj.email}">{obj.email}</a>)'

    class Media:
        js = [forms.Script("orga/js/forms/cfp.js", defer="")]

    class Meta:
        # These are JSON fields on event.settings
        json_fields = {
            "submission_public_review": "feature_flags",
            "speakers_can_edit_submissions": "feature_flags",
            "mail_on_new_submission": "mail_settings",
        }


class CfPForm(ReadOnlyFlag, JsonSubfieldMixin, PretalxI18nModelForm):
    show_deadline = forms.BooleanField(
        label=_("Display deadline publicly"),
        required=False,
        help_text=_("Show the time and date the CfP ends to potential speakers."),
    )
    count_length_in = forms.ChoiceField(
        label=_("Count text length in"),
        choices=(("chars", _("Characters")), ("words", _("Words"))),
        widget=forms.RadioSelect(),
    )

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.event = event

    class Meta:
        model = CfP
        fields = ["headline", "text", "opening", "deadline"]
        # These are JSON fields on cfp.settings
        json_fields = {"show_deadline": "settings", "count_length_in": "settings"}


class CfPFieldConfigForm(PretalxI18nFormMixin, forms.Form):
    label = I18nFormField(
        label=_("Custom label"),
        required=False,
        help_text=_("Leave empty to use the default label."),
        widget=I18nTextInput,
    )
    help_text = I18nFormField(
        label=_("Help text"),
        required=False,
        help_text=_("Additional instructions shown below the field."),
        widget=I18nTextarea,
    )
    visibility = forms.ChoiceField(
        label=_("Visibility"),
        choices=[("required", _("Required")), ("optional", _("Optional"))],
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    min_length = forms.IntegerField(
        label=_("Minimum length"),
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    max_length = forms.IntegerField(
        label=_("Maximum length"),
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    max = forms.IntegerField(
        label=_("Maximum speakers"),
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        help_text=_("Maximum number of speakers per proposal (including submitter)."),
    )
    min_number = forms.IntegerField(
        label=_("Minimum tags"),
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    max_number = forms.IntegerField(
        label=_("Maximum tags"),
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, field_key=None, event=None, **kwargs):
        self.field_key = field_key
        self.event = event
        kwargs["locales"] = event.locales
        super().__init__(*args, **kwargs)

        self.fields["help_text"].widget.attrs["rows"] = "2"
        self.fields["help_text"].widget.attrs["size"] = "2"
        length_fields = ["title", "abstract", "description", "biography"]
        if field_key not in length_fields:
            del self.fields["min_length"]
            del self.fields["max_length"]

        if field_key != "additional_speaker":
            del self.fields["max"]

        if field_key == "tags":
            self.fields["help_text"].help_text = _(
                "Additional instructions shown below the field. "
                "Note: Only public tags will be shown to submitters."
            )
        else:
            del self.fields["min_number"]
            del self.fields["max_number"]

    def clean(self):
        cleaned = super().clean()
        min_number = cleaned.get("min_number")
        max_number = cleaned.get("max_number")
        if min_number and max_number and min_number > max_number:
            raise forms.ValidationError(
                _("Minimum tags cannot be greater than maximum tags.")
            )
        return cleaned


class StepHeaderForm(PretalxI18nFormMixin, forms.Form):
    title = I18nFormField(
        label=_("Step title"),
        required=False,
        help_text=_("Leave empty to use the default title."),
        widget=I18nTextInput,
    )
    text = I18nFormField(
        label=_("Step description"),
        required=False,
        help_text=_("Leave empty to use the default description."),
        widget=I18nTextarea,
    )

    def __init__(self, *args, event=None, **kwargs):
        self.event = event
        kwargs["locales"] = event.locales
        super().__init__(*args, **kwargs)
        self.fields["text"].widget.attrs["rows"] = "3"
