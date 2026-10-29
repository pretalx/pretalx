# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import json
import uuid

import pytest

from pretalx.schedule.interfaces.forms import RoomForm
from tests.factories import AvailabilityFactory, RoomFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _data(name, availabilities=(), capacity=""):
    return {
        "name_0": name,
        "guid": "",
        "description_0": "",
        "speaker_info_0": "",
        "capacity": capacity,
        "availabilities": json.dumps(
            {
                "availabilities": [
                    {"start": start.isoformat(), "end": end.isoformat()}
                    for start, end in availabilities
                ]
            }
        ),
    }


def test_room_form_init(event):
    form = RoomForm(event=event)
    generated_guid = RoomForm(instance=RoomFactory(event=event, guid=None), event=event)
    custom_guid = RoomForm(
        instance=RoomFactory(event=event, guid=uuid.uuid4()), event=event
    )

    assert form.instance.event == event
    assert form.fields["availabilities"].event == event
    assert form.fields["availabilities"].instance == form.instance
    for field in ("name", "description", "speaker_info"):
        assert form.fields[field].widget.attrs.get("placeholder")
    assert generated_guid.instance.event == event
    assert str(generated_guid.instance.uuid) in str(
        generated_guid.fields["guid"].help_text
    )
    assert str(custom_guid.instance.uuid) not in str(
        custom_guid.fields["guid"].help_text or ""
    )


def test_room_form_save_creates_room_and_replaces_availabilities(event):
    start = event.datetime_from + dt.timedelta(hours=2)
    end = event.datetime_to - dt.timedelta(hours=2)

    form = RoomForm(data=_data("Big Hall", capacity="200"), event=event)
    assert form.is_valid(), form.errors
    room = form.save()
    old_avail = AvailabilityFactory(event=event, room=room)

    assert (str(room.name), room.capacity, room.event) == ("Big Hall", 200, event)

    form = RoomForm(
        data=_data("Big Hall", availabilities=[(start, end)]),
        instance=room,
        event=event,
    )
    assert form.is_valid(), form.errors
    form.save()
    avails = list(room.availabilities.all())

    assert [(avail.start, avail.end) for avail in avails] == [(start, end)]
    assert avails[0].pk != old_avail.pk

    form = RoomForm(data=_data("Big Hall"), instance=room, event=event)
    assert form.is_valid(), form.errors
    form.save()

    assert list(room.availabilities.all()) == []


def test_room_form_read_only_disables_fields_and_rejects_changes(event):
    form = RoomForm(data=_data("Sneaky Room"), event=event, read_only=True)

    assert all(field.disabled for field in form.fields.values())
    assert not form.is_valid()
    assert "name" in form.errors
