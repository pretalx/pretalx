# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import json
import uuid

import pytest

from pretalx.schedule.interfaces.forms import RoomForm
from tests.factories import AvailabilityFactory, RoomFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_room_form_init(event):
    """Initializing a RoomForm for a new room configures the instance,
    the availabilities field, and adds placeholders to input widgets."""
    form = RoomForm(event=event)

    assert form.instance.event == event
    assert form.fields["availabilities"].event == event
    assert form.fields["availabilities"].instance == form.instance
    for field in ("name", "description", "speaker_info"):
        assert form.fields[field].widget.attrs.get("placeholder")


def test_room_form_init_preserves_existing_event(event):
    room = RoomFactory(event=event)

    form = RoomForm(instance=room, event=event)

    assert form.instance.event == event


def test_room_form_init_guid_help_text_when_no_guid(event):
    """When a room has a pk but no guid, the guid field shows a help text
    with the auto-generated UUID."""
    room = RoomFactory(event=event, guid=None)

    form = RoomForm(instance=room, event=event)

    assert str(room.uuid) in str(form.fields["guid"].help_text)


def test_room_form_init_guid_no_help_text_when_guid_set(event):
    room = RoomFactory(event=event, guid=uuid.uuid4())

    form = RoomForm(instance=room, event=event)

    assert str(room.uuid) not in str(form.fields["guid"].help_text or "")


def test_room_form_save_creates_room(event):
    event.feature_flags["attendee_signup"] = True
    event.save()
    data = {
        "name_0": "Big Hall",
        "guid": "",
        "description_0": "",
        "speaker_info_0": "",
        "capacity": "200",
        "availabilities": '{"availabilities": []}',
    }
    form = RoomForm(data=data, event=event)
    assert form.is_valid(), form.errors

    room = form.save()

    assert str(room.name) == "Big Hall"
    assert room.capacity == 200
    assert room.event == event


def test_room_form_save_replaces_availabilities(event):
    room = RoomFactory(event=event)
    old_avail = AvailabilityFactory(event=event, room=room)
    new_start = event.datetime_from + dt.timedelta(hours=2)
    new_end = event.datetime_to - dt.timedelta(hours=2)
    avail_json = json.dumps(
        {
            "availabilities": [
                {"start": new_start.isoformat(), "end": new_end.isoformat()}
            ]
        }
    )
    data = {
        "name_0": str(room.name),
        "guid": "",
        "description_0": "",
        "speaker_info_0": "",
        "capacity": "",
        "availabilities": avail_json,
    }

    form = RoomForm(data=data, instance=room, event=event)
    assert form.is_valid(), form.errors
    form.save()
    avails = list(room.availabilities.all())

    assert len(avails) == 1
    assert avails[0].pk != old_avail.pk
    assert avails[0].start == new_start
    assert avails[0].end == new_end


def test_room_form_save_with_no_availabilities_clears_existing(event):
    room = RoomFactory(event=event)
    AvailabilityFactory(event=event, room=room)
    data = {
        "name_0": str(room.name),
        "guid": "",
        "description_0": "",
        "speaker_info_0": "",
        "capacity": "",
        "availabilities": '{"availabilities": []}',
    }

    form = RoomForm(data=data, instance=room, event=event)
    assert form.is_valid(), form.errors
    form.save()
    avails = list(room.availabilities.all())

    assert avails == []


def test_room_form_read_only_disables_all_fields(event):
    form = RoomForm(event=event, read_only=True)

    for field in form.fields.values():
        assert field.disabled is True


def test_room_form_read_only_rejects_changes(event):
    """A read-only RoomForm ignores submitted data, so required fields
    fail validation."""
    data = {
        "name_0": "Sneaky Room",
        "guid": "",
        "description_0": "",
        "speaker_info_0": "",
        "capacity": "",
        "availabilities": '{"availabilities": []}',
    }

    form = RoomForm(data=data, event=event, read_only=True)

    assert not form.is_valid()
    assert "name" in form.errors


@pytest.mark.parametrize(("feature_on", "expect_field"), ((True, True), (False, False)))
def test_room_form_capacity_field_follows_signup_feature(
    event, feature_on, expect_field
):
    event.feature_flags["attendee_signup"] = feature_on
    event.save()

    form = RoomForm(event=event)

    assert ("capacity" in form.fields) is expect_field
