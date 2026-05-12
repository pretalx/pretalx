# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.utils.translation import gettext_lazy as _

from pretalx.common.forms.renderers import InlineFormLabelRenderer
from pretalx.common.forms.widgets import EnhancedSelect
from pretalx.common.text.phrases import phrases


class SubmissionStateChangeForm(forms.Form):
    pending = forms.BooleanField(
        label=_("Mark the new state as “pending”"),
        help_text=_(
            "If you mark state changes as pending, they will not be visible to speakers right away. You can always apply pending changes for some or all proposals in one go once you are ready to make your decisions public."
        ),
        required=False,
        initial=False,
    )


class AddSpeakerForm(forms.Form):
    email = forms.EmailField(
        label=phrases.cfp.speaker_email,
        help_text=_(
            "The email address of the speaker holding the session. They will be invited to create an account."
        ),
        required=False,
        widget=forms.Select,
    )
    name = forms.CharField(
        label=_("Speaker name"),
        help_text=_("The name of the speaker that should be displayed publicly."),
        required=False,
    )
    locale = forms.ChoiceField(
        label=_("Invite language"),
        choices=[],
        required=False,
        help_text=_(
            "The language in which the speaker will receive their invitation email."
        ),
        widget=EnhancedSelect,
    )

    class Media:
        js = [
            forms.Script("vendored/choices/choices.min.js", defer=""),
            forms.Script("orga/js/forms/usersearch.js", defer=""),
        ]
        css = {
            "all": ["vendored/choices/choices.min.css", "common/css/forms/select.css"]
        }

    def __init__(self, *args, event=None, form_renderer=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not event.named_locales or len(event.named_locales) < 2:
            self.fields.pop("locale")
        else:
            self.fields["locale"].choices = event.named_locales
            self.fields["locale"].initial = event.locale

    def clean(self):
        data = super().clean()
        if data.get("name") and not data.get("email"):
            raise forms.ValidationError(_("Please provide an email address."))
        return data


class AddSpeakerInlineForm(AddSpeakerForm):
    default_renderer = InlineFormLabelRenderer
