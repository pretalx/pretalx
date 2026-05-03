# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.utils.translation import gettext_lazy as _

from pretalx.common.text.phrases import phrases
from pretalx.submission.domain.invitation import send_invitation
from pretalx.submission.interfaces.validators.speaker import (
    validate_speakers_within_limit,
)


class SubmissionInvitationForm(forms.Form):
    speaker = forms.EmailField(label=phrases.cfp.speaker_email)

    def __init__(self, submission, speaker, *args, **kwargs):
        self.submission = submission
        self.speaker = speaker
        self.invitation = None
        super().__init__(*args, **kwargs)

    def clean_speaker(self):
        email = self.cleaned_data["speaker"].strip().lower()
        if self.submission.speakers.filter(user__email__iexact=email).exists():
            raise forms.ValidationError(
                _("This person is already a speaker on this proposal.")
            )
        if self.submission.invitations.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                _("This person has already been invited to this proposal.")
            )
        validate_speakers_within_limit(
            self.submission.event,
            current=self.submission.speakers.count(),
            pending=self.submission.invitations.count(),
            additional=1,
        )
        return email

    def save(self):
        self.invitation = send_invitation(
            self.submission, email=self.cleaned_data["speaker"], sender=self.speaker
        )
        return self.invitation
