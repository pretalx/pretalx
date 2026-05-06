# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

from django import forms
from django_scopes.forms import SafeModelChoiceField

from pretalx.common.forms.widgets import HtmlDateInput, HtmlTimeInput
from pretalx.schedule.domain.slot import move_slot
from pretalx.schedule.models import TalkSlot


class QuickScheduleForm(forms.ModelForm):
    start_date = forms.DateField(widget=HtmlDateInput)
    start_time = forms.TimeField(widget=HtmlTimeInput)

    def __init__(self, *args, event, **kwargs):
        self.event = event
        super().__init__(*args, **kwargs)
        self.fields["room"].queryset = self.event.rooms.all()
        if self.instance.start:
            self.fields["start_date"].initial = self.instance.start.date()
            self.fields["start_time"].initial = self.instance.start.time()
        else:
            self.fields["start_date"].initial = event.date_from

    def save(self):
        start = dt.datetime.combine(
            self.cleaned_data["start_date"],
            self.cleaned_data["start_time"],
            tzinfo=self.event.tz,
        )
        return move_slot(self.instance, start)

    class Meta:
        model = TalkSlot
        fields = ("room",)
        field_classes = {"room": SafeModelChoiceField}
