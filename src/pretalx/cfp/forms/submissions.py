# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.utils.translation import gettext_lazy as _

from pretalx.common.text.phrases import phrases
from pretalx.submission.models import SubmissionInvitation


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
        max_speakers = self.submission.event.cfp.max_speakers
        if max_speakers is not None:
            current = self.submission.speakers.count()
            pending = self.submission.invitations.count()
            if current + pending + 1 > max_speakers:
                raise forms.ValidationError(
                    _(
                        "This would exceed the maximum of {max} speakers per proposal."
                    ).format(max=max_speakers)
                )

        return email

    def save(self):
        email = self.cleaned_data["speaker"]
        self.invitation, created = SubmissionInvitation.objects.get_or_create(
            submission=self.submission, email=email
        )
        if not created:
            return self.invitation
        self.invitation.send(_from=self.speaker)
        return self.invitation
