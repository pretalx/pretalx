import datetime as dt
import json
import uuid

import pytest
from django_scopes import scopes_disabled

from pretalx.schedule.forms import QuickScheduleForm, RoomForm
from tests.factories import (
    AvailabilityFactory,
    RoomFactory,
    SubmissionFactory,
    TalkSlotFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_room_form_init(event):
    """Initializing a RoomForm for a new room configures the instance,
    the availabilities field, and adds placeholders to input widgets."""
    form = RoomForm(event=event)

    assert form.instance.event == event
    assert form.fields["availabilities"].event == event
    assert form.fields["availabilities"].instance == form.instance
    for field in ("name", "description", "speaker_info", "capacity"):
        assert form.fields[field].widget.attrs.get("placeholder")


@pytest.mark.django_db
def test_room_form_init_preserves_existing_event(event):
    """When editing an existing room, the instance's event is not overwritten."""
    room = RoomFactory(event=event)

    with scopes_disabled():
        form = RoomForm(instance=room, event=event)

    assert form.instance.event == event


@pytest.mark.django_db
def test_room_form_init_guid_help_text_when_no_guid(event):
    """When a room has a pk but no guid, the guid field shows a help text
    with the auto-generated UUID."""
    room = RoomFactory(event=event, guid=None)

    with scopes_disabled():
        form = RoomForm(instance=room, event=event)

    assert str(room.uuid) in str(form.fields["guid"].help_text)


@pytest.mark.django_db
def test_room_form_init_guid_no_help_text_when_guid_set(event):
    """When a room has a guid set, no special help text is added."""
    room = RoomFactory(event=event, guid=uuid.uuid4())

    with scopes_disabled():
        form = RoomForm(instance=room, event=event)

    assert str(room.uuid) not in str(form.fields["guid"].help_text or "")


@pytest.mark.django_db
def test_room_form_save_creates_room(event):
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

    with scopes_disabled():
        room = form.save()

    assert str(room.name) == "Big Hall"
    assert room.capacity == 200
    assert room.event == event


@pytest.mark.django_db
def test_room_form_save_replaces_availabilities(event):
    """Existing availabilities are replaced by the submitted ones."""
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

    with scopes_disabled():
        form = RoomForm(data=data, instance=room, event=event)
        assert form.is_valid(), form.errors
        form.save()
        avails = list(room.availabilities.all())

    assert len(avails) == 1
    assert avails[0].pk != old_avail.pk
    assert avails[0].start == new_start
    assert avails[0].end == new_end


@pytest.mark.django_db
def test_room_form_save_with_no_availabilities_clears_existing(event):
    """When empty availabilities list is submitted, existing availabilities
    are cleared."""
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

    with scopes_disabled():
        form = RoomForm(data=data, instance=room, event=event)
        assert form.is_valid(), form.errors
        form.save()
        avails = list(room.availabilities.all())

    assert avails == []


@pytest.mark.django_db
def test_room_form_read_only_disables_all_fields(event):
    form = RoomForm(event=event, read_only=True)

    for field in form.fields.values():
        assert field.disabled is True


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_quick_schedule_form_init_room_queryset(event):
    """The room field queryset is scoped to the event's rooms."""
    room = RoomFactory(event=event)
    RoomFactory()  # room on another event, should not appear
    submission = SubmissionFactory(event=event)
    slot = TalkSlotFactory(submission=submission, room=room)

    with scopes_disabled():
        form = QuickScheduleForm(event=event, instance=slot)

    assert list(form.fields["room"].queryset) == [room]


@pytest.mark.django_db
def test_quick_schedule_form_init_with_existing_start(event):
    """When a slot has a start time, date and time fields are pre-filled."""
    submission = SubmissionFactory(event=event)
    slot = TalkSlotFactory(submission=submission)

    with scopes_disabled():
        form = QuickScheduleForm(event=event, instance=slot)

    assert form.fields["start_date"].initial == slot.start.date()
    assert form.fields["start_time"].initial == slot.start.time()


@pytest.mark.django_db
def test_quick_schedule_form_init_without_start(event):
    """When a slot has no start time, date defaults to event date_from
    and time has no initial."""
    submission = SubmissionFactory(event=event)
    slot = TalkSlotFactory(submission=submission, start=None, end=None)

    with scopes_disabled():
        form = QuickScheduleForm(event=event, instance=slot)

    assert form.fields["start_date"].initial == event.date_from
    assert form.fields["start_time"].initial is None


@pytest.mark.django_db
@pytest.mark.parametrize("explicit_duration", (45, None))
def test_quick_schedule_form_save_sets_start_and_end(event, explicit_duration):
    """save() combines start_date and start_time into a start datetime
    and calculates end from submission duration (explicit or type default)."""
    room = RoomFactory(event=event)
    submission = SubmissionFactory(event=event, duration=explicit_duration)
    expected_duration = explicit_duration or submission.submission_type.default_duration
    slot = TalkSlotFactory(submission=submission, room=room)
    start_date = event.date_from
    start_time = dt.time(10, 30)

    data = {
        "room": room.pk,
        "start_date": start_date.isoformat(),
        "start_time": start_time.strftime("%H:%M"),
    }
    with scopes_disabled():
        form = QuickScheduleForm(event=event, instance=slot, data=data)
        assert form.is_valid(), form.errors
        saved_slot = form.save()

    expected_start = dt.datetime.combine(start_date, start_time, tzinfo=event.tz)
    expected_end = expected_start + dt.timedelta(minutes=expected_duration)
    assert saved_slot.start == expected_start
    assert saved_slot.end == expected_end
