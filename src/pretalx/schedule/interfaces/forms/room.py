# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.utils.translation import gettext_lazy as _

from pretalx.common.forms.fields import AvailabilitiesField
from pretalx.common.forms.mixins import PretalxI18nModelForm, ReadOnlyFlag
from pretalx.schedule.models import Room


class RoomForm(ReadOnlyFlag, PretalxI18nModelForm):
    availabilities = AvailabilitiesField(
        resolution="00:15:00", label=_("Availability"), required=False
    )

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)

        if not getattr(self.instance, "event", None):
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
            + _("All times are in the event timezone, {tz}.").format(tz=event.timezone)
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
        if not event.get_feature_flag("attendee_signup"):
            self.fields.pop("capacity", None)
        else:
            self.fields["capacity"].widget.attrs["placeholder"] = "300"
        if not self.instance._state.adding and not self.instance.guid:
            self.fields["guid"].help_text = _(
                "The current, automatically generated GUID is: {guid}."
            ).format(guid=self.instance.uuid)

    def save(self, *args, **kwargs):
        instance = super().save(*args, **kwargs)
        self.fields["availabilities"].save(
            instance, self.cleaned_data.get("availabilities")
        )
        return instance

    class Meta:
        model = Room
        fields = ["name", "guid", "description", "speaker_info", "capacity"]
