# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

from django import forms
from django.utils.translation import gettext_lazy as _
from django_scopes.forms import SafeModelChoiceField

from pretalx.common.forms.fields import AvailabilitiesField
from pretalx.common.forms.mixins import PretalxI18nModelForm, ReadOnlyFlag
from pretalx.common.forms.widgets import HtmlDateInput, HtmlTimeInput
from pretalx.schedule.models import Availability, Room, TalkSlot


class RoomForm(ReadOnlyFlag, PretalxI18nModelForm):
    availabilities = AvailabilitiesField(
        resolution="00:15:00",
        label=_("Availability"),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        event = kwargs.pop("event", None)
        super().__init__(*args, **kwargs)

        if not hasattr(self.instance, "event") or not self.instance.event:
            self.instance.event = event

        self.fields["availabilities"].instance = self.instance
        self.fields["availabilities"].event = event
        self.fields["availabilities"].set_initial_from_instance()
        self.fields["availabilities"].help_text = (
            _(
                "Please click and drag to mark your availability during the conference with green blocks. "
                "We will try to schedule your slot during these times. You can click a block twice to remove it."
            )
            + " "
            + _("Please note that all times are in the event timezone, {tz}.").format(
                tz=event.timezone if event else ""
            )
            + " "
            + _(
                "If you set room availabilities, speakers will only be able to set their availability for when any room is available."
            )
        )

        self.fields["name"].widget.attrs["placeholder"] = _("Room I")
        self.fields["description"].widget.attrs["placeholder"] = _(
            "Description, e.g.: Our main meeting place, Room I, enter from the right."
        )
        self.fields["speaker_info"].widget.attrs["placeholder"] = _(
            "Information for speakers, e.g.: Projector has only HDMI input."
        )
        self.fields["capacity"].widget.attrs["placeholder"] = "300"
        if self.instance.pk and not self.instance.guid:
            self.fields["guid"].help_text = _(
                "The current, automatically generated GUID is: {guid}."
            ).format(guid=self.instance.uuid)

    def save(self, *args, **kwargs):
        instance = super().save(*args, **kwargs)
        availabilities = self.cleaned_data.get("availabilities")

        if availabilities is not None:
            Availability.replace_for_instance(instance, availabilities)

        return instance

    class Meta:
        model = Room
        fields = ["name", "guid", "description", "speaker_info", "capacity"]


class QuickScheduleForm(forms.ModelForm):
    start_date = forms.DateField(widget=HtmlDateInput)
    start_time = forms.TimeField(widget=HtmlTimeInput)

    def __init__(self, event, *args, **kwargs):
        self.event = event
        super().__init__(*args, **kwargs)
        self.fields["room"].queryset = self.event.rooms.all()
        if self.instance.start:
            self.fields["start_date"].initial = self.instance.start.date()
            self.fields["start_time"].initial = self.instance.start.time()
        else:
            self.fields["start_date"].initial = event.date_from

    def save(self):
        talk = self.instance
        talk.start = dt.datetime.combine(
            self.cleaned_data["start_date"],
            self.cleaned_data["start_time"],
            tzinfo=self.event.tz,
        )
        talk.end = talk.start + dt.timedelta(minutes=talk.submission.get_duration())
        return super().save()

    class Meta:
        model = TalkSlot
        fields = ("room",)
        field_classes = {
            "room": SafeModelChoiceField,
        }
