# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.utils.translation import gettext_lazy as _

from pretalx.common.forms.fields import HoneypotField
from pretalx.common.forms.renderers import InlineFormRenderer
from pretalx.person.models import SpeakerProfile
from pretalx.submission.domain.feedback import create_feedback
from pretalx.submission.models import Feedback


class FeedbackForm(forms.ModelForm):
    default_renderer = InlineFormRenderer
    subject = HoneypotField()
    speaker = forms.ModelChoiceField(
        queryset=SpeakerProfile.objects.none(),
        required=False,
        empty_label=_("All speakers"),
    )

    def __init__(self, *, talk, **kwargs):
        super().__init__(**kwargs)
        self.talk = talk
        self.instance.talk = talk
        speakers = talk.speakers.all()
        self.fields["speaker"].queryset = speakers
        self.fields["speaker"].label_from_instance = lambda obj: obj.get_display_name()
        if len(speakers) == 1:
            self.fields["speaker"].widget = forms.HiddenInput()

    def save(self, *args, **kwargs):
        return create_feedback(self.instance)

    class Meta:
        model = Feedback
        fields = ["speaker", "review"]
