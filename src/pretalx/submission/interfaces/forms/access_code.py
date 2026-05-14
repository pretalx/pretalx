# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.utils.translation import gettext_lazy as _
from django_scopes.forms import SafeModelMultipleChoiceField

from pretalx.common.forms.widgets import EnhancedSelectMultiple, HtmlDateTimeInput
from pretalx.common.text.formatting import format_map
from pretalx.common.text.phrases import phrases
from pretalx.mail.domain.context import get_mail_context
from pretalx.mail.domain.render import get_prefixed_subject
from pretalx.submission.models import SubmissionType, SubmitterAccessCode, Track


class SubmitterAccessCodeForm(forms.ModelForm):
    def __init__(self, *args, event, **kwargs):
        self.event = event
        initial = kwargs.get("initial", {})
        if not kwargs.get("instance"):
            initial["code"] = SubmitterAccessCode.generate_code()
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
        self.fields["submission_types"].queryset = SubmissionType.objects.filter(
            event=self.event
        )
        if event.has_active_tracks:
            self.fields["tracks"].queryset = Track.objects.filter(event=self.event)
        else:
            self.fields.pop("tracks")

    class Meta:
        model = SubmitterAccessCode
        fields = (
            "code",
            "valid_until",
            "maximum_uses",
            "tracks",
            "submission_types",
            "internal_notes",
        )
        field_classes = {
            "tracks": SafeModelMultipleChoiceField,
            "submission_types": SafeModelMultipleChoiceField,
        }
        widgets = {
            "valid_until": HtmlDateTimeInput,
            "tracks": EnhancedSelectMultiple,
            "submission_types": EnhancedSelectMultiple,
        }


class AccessCodeSendForm(forms.Form):
    to = forms.EmailField(label=_("To"))
    subject = forms.CharField(label=phrases.base.email_subject)
    text = forms.CharField(widget=forms.Textarea(), label=phrases.base.text_body)

    def __init__(self, *args, instance, user, **kwargs):
        event_name = str(instance.event.name)
        subject = _("Access code for the {event_name} CfP").format(
            event_name=event_name
        )
        text_template = (
            _("""Hi!

This is an access code for the {event_name} CfP.""").format(event_name=event_name)
            + " "
        )
        tracks = list(instance.tracks.all())
        if tracks:
            track_names = ", ".join(str(t.name) for t in tracks)
            text_template += (
                _(
                    "It will allow you to submit a proposal to the following track(s): {tracks}."
                ).format(tracks=track_names)
                + " "
            )
        submission_types = list(instance.submission_types.all())
        if submission_types:
            type_names = ", ".join(str(t.name) for t in submission_types)
            text_template += (
                _("It is valid for the following session type(s): {types}.").format(
                    types=type_names
                )
                + " "
            )
        if not tracks and not submission_types:
            text_template += (
                str(_("It will allow you to submit a proposal to our CfP.")) + " "
            )
        if instance.valid_until:
            text_template += (
                str(
                    _("This access code is valid until {date}.").format(
                        date=instance.valid_until.strftime("%Y-%m-%d %H:%M")
                    )
                )
                + " "
            )
        text_template += _("""
Please follow this URL to use the code:

  {url}

I’m looking forward to your proposal!
{inviting_speaker}""")
        context = get_mail_context(
            event=instance.event,
            inviting_user=user,
            safe_extra_context={"url": instance.urls.cfp_url},
        )
        initial = kwargs.get("initial", {})
        initial["subject"] = get_prefixed_subject(instance.event, subject)
        initial["text"] = format_map(text_template, context)
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
