# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.utils.translation import gettext_lazy as _

from pretalx.common.text.phrases import phrases
from pretalx.mail.models import get_prefixed_subject
from pretalx.submission.models import SubmissionInvitation


class SubmissionInvitationForm(forms.Form):
    speaker = forms.EmailField(label=phrases.cfp.speaker_email)
    subject = forms.CharField(label=phrases.base.email_subject)
    text = forms.CharField(widget=forms.Textarea(), label=phrases.base.text_body)

    def __init__(self, submission, speaker, *args, **kwargs):
        self.submission = submission
        self.speaker = speaker
        self.invitation = None
        initial = kwargs.get("initial", {})
        subject = phrases.cfp.invite_subject.format(speaker=speaker.get_display_name())
        initial["subject"] = get_prefixed_subject(submission.event, subject)
        initial["text"] = phrases.cfp.invite_text.format(
            event=submission.event.name,
            title=submission.title,
            url="{invitation_url}",  # Placeholder, will be replaced in save
            speaker=speaker.get_display_name(),
        )
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)

    def clean_text(self):
        text = self.cleaned_data["text"]
        if not text or "{invitation_url}" not in text:
            raise forms.ValidationError(
                _("You must include the “{invitation_url}” placeholder in your email.")
            )
        return text

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
            submission=self.submission,
            email=email,
        )
        if not created:  # pragma: no cover
            return self.invitation

        text = self.cleaned_data["text"].replace(
            "{invitation_url}", self.invitation.urls.base.full()
        )

        self.invitation.send(
            _from=self.speaker,
            subject=self.cleaned_data["subject"],
            text=text,
        )
        return self.invitation
