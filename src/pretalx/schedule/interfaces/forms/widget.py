# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

from django import forms
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from pretalx.common.forms.mixins import JsonSubfieldMixin
from pretalx.common.forms.widgets import EnhancedSelect, EnhancedSelectMultiple
from pretalx.common.text.phrases import phrases
from pretalx.event.models import Event
from pretalx.schedule.models import Room


class WidgetSettingsForm(JsonSubfieldMixin, forms.Form):
    show_widget_if_not_public = forms.BooleanField(
        label=_("Show the widget even if the schedule is not public"),
        help_text=_(
            "Set to allow external pages to show the schedule widget, even if the schedule is not shown here using pretalx."
        ),
        required=False,
    )

    class Media:
        js = [forms.Script("orga/js/forms/widget.js", defer="")]

    class Meta:
        json_fields = {"show_widget_if_not_public": "feature_flags"}


class WidgetGenerationForm(forms.ModelForm):
    schedule_display = forms.ChoiceField(
        label=phrases.orga.event_schedule_format_label,
        choices=(
            ("grid", pgettext_lazy("schedule display format", "Grid")),
            ("list", pgettext_lazy("schedule display format", "List")),
        ),
        required=True,
    )
    days = forms.MultipleChoiceField(
        label=_("Limit days"),
        choices=[],
        widget=EnhancedSelectMultiple,
        required=False,
        help_text=_(
            "You can limit the days shown in the widget. Leave empty to show all days."
        ),
    )
    rooms = forms.ModelMultipleChoiceField(
        label=_("Limit rooms"),
        queryset=Room.objects.none(),
        widget=EnhancedSelectMultiple,
        required=False,
        help_text=_(
            "You can limit the rooms shown in the widget. Leave empty to show all rooms."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["locale"].label = _("Widget language")
        event = self.instance
        self.fields["days"].choices = [
            (
                event.date_from + dt.timedelta(days=i),
                event.date_from + dt.timedelta(days=i),
            )
            for i in range(event.duration)
        ]
        self.fields["rooms"].queryset = event.rooms.all()

    class Meta:
        model = Event
        fields = ["locale"]
        widgets = {"locale": EnhancedSelect}
