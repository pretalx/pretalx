# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms

from pretalx.common.text.phrases import phrases
from pretalx.mail.models import get_prefixed_subject


class SubmissionInvitationForm(forms.Form):
    speaker = forms.EmailField(label=phrases.cfp.speaker_email)
    subject = forms.CharField(label=phrases.base.email_subject)
    text = forms.CharField(widget=forms.Textarea(), label=phrases.base.text_body)

    def __init__(self, submission, speaker, *args, **kwargs):
        self.submission = submission
        initial = kwargs.get("initial", {})
        subject = phrases.cfp.invite_subject.format(speaker=speaker.get_display_name())
        initial["subject"] = get_prefixed_subject(submission.event, subject)
        initial["text"] = phrases.cfp.invite_text.format(
            event=submission.event.name,
            title=submission.title,
            url=submission.urls.accept_invitation.full(),
            speaker=speaker.get_display_name(),
        )
        super().__init__(*args, **kwargs)

    def save(self):
        self.submission.send_invite(
            to=self.cleaned_data["speaker"].strip(),
            subject=self.cleaned_data["subject"],
            text=self.cleaned_data["text"],
        )
