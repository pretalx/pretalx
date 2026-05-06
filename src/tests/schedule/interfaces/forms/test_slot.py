# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest

from pretalx.schedule.interfaces.forms import QuickScheduleForm
from tests.factories import RoomFactory, SubmissionFactory, TalkSlotFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_quick_schedule_form_init_room_queryset(event):
    room = RoomFactory(event=event)
    RoomFactory()  # room on another event, should not appear
    submission = SubmissionFactory(event=event)
    slot = TalkSlotFactory(submission=submission, room=room)

    form = QuickScheduleForm(event=event, instance=slot)

    assert list(form.fields["room"].queryset) == [room]


def test_quick_schedule_form_init_with_existing_start(event):
    submission = SubmissionFactory(event=event)
    slot = TalkSlotFactory(submission=submission)

    form = QuickScheduleForm(event=event, instance=slot)

    assert form.fields["start_date"].initial == slot.start.date()
    assert form.fields["start_time"].initial == slot.start.time()


def test_quick_schedule_form_init_without_start(event):
    """When a slot has no start time, date defaults to event date_from
    and time has no initial."""
    submission = SubmissionFactory(event=event)
    slot = TalkSlotFactory(submission=submission, start=None, end=None)

    form = QuickScheduleForm(event=event, instance=slot)

    assert form.fields["start_date"].initial == event.date_from
    assert form.fields["start_time"].initial is None


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
    form = QuickScheduleForm(event=event, instance=slot, data=data)
    assert form.is_valid(), form.errors
    saved_slot = form.save()

    expected_start = dt.datetime.combine(start_date, start_time, tzinfo=event.tz)
    expected_end = expected_start + dt.timedelta(minutes=expected_duration)
    assert saved_slot.start == expected_start
    assert saved_slot.end == expected_end
