# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.utils.translation import gettext_lazy as _

from pretalx.common.forms.mixins import ReadOnlyFlag
from pretalx.common.forms.widgets import EnhancedSelectMultiple, MultiEmailInput
from pretalx.mail.models import QueuedMail
from pretalx.person.domain.queries.profile import (
    filter_reachable,
    speaker_by_email,
    submitters_for_event,
)
from pretalx.person.models import SpeakerProfile


class MailDetailForm(ReadOnlyFlag, forms.ModelForm):
    to_speakers = forms.ModelMultipleChoiceField(
        queryset=SpeakerProfile.objects.none(),
        required=False,
        widget=EnhancedSelectMultiple,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance or not self.instance.to_speakers.count():
            self.fields.pop("to_speakers")
        else:
            speakers_field = self.fields["to_speakers"]
            speakers_field.queryset = filter_reachable(
                submitters_for_event(self.instance.event, include_bare=True)
            )
            speakers_field.required = False
            speakers_field.label_from_instance = lambda obj: obj.get_display_name()

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean(*args, **kwargs)
        if not cleaned_data["to"] and not cleaned_data.get("to_speakers"):
            self.add_error(
                "to",
                forms.ValidationError(
                    _("An email needs to have at least one recipient.")
                ),
            )
        return cleaned_data

    def save(self, *args, **kwargs):
        # The organiser has eyes on the plain-text body now; any cached
        # HTML rendering is stale. Drop it so delivery_html() falls back
        # to regenerating from the edited text at send time. This removes
        # some escaping, as we now have to assume that all content in
        # the text is meant to be parsed as Markdown and is trusted, as
        # it has been reviewed and modified by an organiser.
        if self.has_changed() and "text" in self.changed_data:
            self.instance.text_html = None
        obj = super().save(*args, **kwargs)
        if self.has_changed() and "to" in self.changed_data:
            addresses = list(
                {
                    address.strip().lower()
                    for address in (obj.to or "").split(",")
                    if address.strip()
                }
            )
            found_addresses = []
            for address in addresses:
                speaker = speaker_by_email(obj.event, address)
                if speaker:
                    obj.to_speakers.add(speaker)
                    found_addresses.append(address)
            addresses = set(addresses) - set(found_addresses)
            addresses = ",".join(addresses) if addresses else ""
            obj.to = addresses
            obj.save()
        return obj

    class Meta:
        model = QueuedMail
        fields = ["to", "to_speakers", "reply_to", "cc", "bcc", "subject", "text"]
        widgets = {
            "to_speakers": EnhancedSelectMultiple,
            "to": MultiEmailInput,
            "reply_to": MultiEmailInput,
            "cc": MultiEmailInput,
            "bcc": MultiEmailInput,
        }
