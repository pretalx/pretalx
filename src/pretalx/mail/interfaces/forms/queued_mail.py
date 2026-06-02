# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.db.models import Count, Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from pretalx.common.forms.fields import CountableOption
from pretalx.common.forms.mixins import ReadOnlyFlag
from pretalx.common.forms.renderers import InlineFormRenderer
from pretalx.common.forms.widgets import (
    EnhancedSelectMultiple,
    MultiEmailInput,
    SelectMultipleWithCount,
)
from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.models import QueuedMail
from pretalx.person.models import User
from pretalx.submission.models import Track


class MailDetailForm(ReadOnlyFlag, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance or not self.instance.to_users.count():
            self.fields.pop("to_users")
        else:
            self.fields["to_users"].queryset = User.objects.filter(
                profiles__in=self.instance.event.submitters
            ).distinct()
            self.fields["to_users"].required = False

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean(*args, **kwargs)
        if not cleaned_data["to"] and not cleaned_data.get("to_users"):
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
                user = User.objects.filter(email__iexact=address).first()
                if user:
                    obj.to_users.add(user)
                    found_addresses.append(address)
            addresses = set(addresses) - set(found_addresses)
            addresses = ",".join(addresses) if addresses else ""
            obj.to = addresses
            obj.save()
        return obj

    class Meta:
        model = QueuedMail
        fields = ["to", "to_users", "reply_to", "cc", "bcc", "subject", "text"]
        widgets = {
            "to_users": EnhancedSelectMultiple,
            "to": MultiEmailInput,
            "reply_to": MultiEmailInput,
            "cc": MultiEmailInput,
            "bcc": MultiEmailInput,
        }


class QueuedMailFilterForm(forms.Form):
    status = forms.MultipleChoiceField(
        required=False,
        widget=SelectMultipleWithCount(
            attrs={"title": pgettext_lazy("email delivery status", "Status")}
        ),
    )
    track = forms.ModelMultipleChoiceField(
        required=False,
        queryset=Track.objects.none(),
        widget=SelectMultipleWithCount(
            attrs={"title": _("Tracks")}, color_field="color", count_attr="mail_count"
        ),
    )

    default_renderer = InlineFormRenderer

    def __init__(self, *args, event=None, sent=None, **kwargs):
        self.event = event
        super().__init__(*args, **kwargs)

        if sent:
            self.fields.pop("status")
        else:
            counts = event.queued_mails.filter(state=QueuedMailStates.DRAFT).aggregate(
                total=Count("pk"),
                failed=Count("pk", filter=Q(error_data__isnull=False)),
            )
            failed_count = counts["failed"]
            pending_count = counts["total"] - failed_count
            if not failed_count:
                self.fields.pop("status")
            else:
                self.fields["status"].choices = [
                    (
                        "draft",
                        CountableOption(
                            pgettext_lazy("email status: not yet sent", "Pending"),
                            pending_count,
                        ),
                    ),
                    (
                        "failed",
                        CountableOption(
                            pgettext_lazy("email status", "Failed"), failed_count
                        ),
                    ),
                ]

        if not event.has_active_tracks:
            self.fields.pop("track")
        else:
            mail_filter = Q(submissions__mails__event=event)
            if sent is not None:
                if sent:
                    mail_filter &= Q(
                        submissions__mails__state__in=[
                            QueuedMailStates.SENT,
                            QueuedMailStates.SENDING,
                        ]
                    )
                else:
                    mail_filter &= Q(submissions__mails__state=QueuedMailStates.DRAFT)

            self.fields["track"].queryset = event.tracks.annotate(
                mail_count=Count(
                    "submissions__mails", distinct=True, filter=mail_filter
                )
            ).order_by("-mail_count")

    def filter_queryset(self, qs):
        status = self.cleaned_data.get("status")
        if status:
            qs = qs.filter(computed_state__in=status)
        tracks = self.cleaned_data.get("track")
        if tracks:
            qs = qs.filter(submissions__track__in=tracks)
        return qs.distinct()

    class Media:
        css = {"all": ["orga/css/forms/search.css"]}
