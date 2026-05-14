# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms

from pretalx.common.text.phrases import phrases
from pretalx.submission.validators.speaker import validate_invitation_target


class SubmissionInvitationForm(forms.Form):
    speaker = forms.EmailField(label=phrases.cfp.speaker_email)

    def __init__(self, *args, submission, **kwargs):
        self.submission = submission
        super().__init__(*args, **kwargs)

    def clean_speaker(self):
        email = self.cleaned_data["speaker"].strip().lower()
        validate_invitation_target(self.submission, email)
        return email
