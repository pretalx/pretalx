# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.utils.translation import gettext_lazy as _

from pretalx.common.forms.renderers import InlineFormRenderer
from pretalx.submission.models import Feedback


class FeedbackForm(forms.ModelForm):
    default_renderer = InlineFormRenderer

    def __init__(self, talk, **kwargs):
        super().__init__(**kwargs)
        self.instance.talk = talk
        speakers = talk.speakers.all()
        self.fields["speaker"].queryset = speakers
        self.fields["speaker"].empty_label = _("All speakers")
        if len(speakers) == 1:
            self.fields["speaker"].widget = forms.HiddenInput()

    def save(self, *args, **kwargs):
        if (
            not self.cleaned_data["speaker"]
            and self.instance.talk.speakers.count() == 1
        ):
            self.instance.speaker = self.instance.talk.speakers.first()
        return super().save(*args, **kwargs)

    class Meta:
        model = Feedback
        fields = ["speaker", "review"]
