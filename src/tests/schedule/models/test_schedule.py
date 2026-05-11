# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django_scopes import scope

from pretalx.schedule.domain.release import freeze_schedule
from pretalx.schedule.models import Schedule
from pretalx.schedule.models.slot import SlotType
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    AvailabilityFactory,
    EventFactory,
    RoomFactory,
    ScheduleFactory,
    SubmissionFactory,
    TalkSlotFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("version", "expected_suffix"),
    ((None, "version=None"), ("v1", "version=v1")),
    ids=["no_version", "with_version"],
)
def test_schedule_str(version, expected_suffix):
    schedule = ScheduleFactory(version=version)
    assert str(schedule) == f"Schedule(event={schedule.event.slug}, {expected_suffix})"


@pytest.mark.parametrize(
    ("version", "expected"),
    ((None, "wip"), ("v2", "v2")),
    ids=["none_returns_wip", "returns_version"],
)
def test_schedule_version_with_fallback(version, expected):
    schedule = ScheduleFactory(version=version)
    assert schedule.version_with_fallback == expected


@pytest.mark.parametrize(
    ("version", "expected"),
    ((None, "wip"), ("v1", "v1"), ("version 1", "version%201")),
    ids=["wip", "plain", "encoded"],
)
def test_schedule_url_version(version, expected):
    schedule = ScheduleFactory(version=version)
    assert schedule.url_version == expected


def test_schedule_is_archived_no_version(event):
    with scope(event=event):
        assert not event.wip_schedule.is_archived


def test_schedule_is_archived_current(event):
    with scope(event=event):
        freeze_schedule(event.wip_schedule, name="v1")
        v1 = Schedule.objects.get(event=event, version="v1")
        assert not v1.is_archived


def test_schedule_is_archived_old(event):
    with scope(event=event):
        freeze_schedule(event.wip_schedule, name="v1")
        freeze_schedule(event.wip_schedule, name="v2")
        v1 = Schedule.objects.get(event=event, version="v1")
        assert v1.is_archived


def test_schedule_scheduled_talks_filters_visible(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    room = RoomFactory(event=event)
    with scope(event=event):
        schedule = event.wip_schedule
    slot = TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
        is_visible=True,
    )
    TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=event.datetime_from + dt.timedelta(hours=2),
        end=event.datetime_from + dt.timedelta(hours=3),
        is_visible=False,
    )

    with scope(event=event):
        result = list(schedule.scheduled_talks)

    assert result == [slot]


def test_schedule_scheduled_talks_excludes_no_room(event):
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(
        submission=submission, schedule=schedule, room=None, is_visible=True
    )

    with scope(event=event):
        assert list(schedule.scheduled_talks) == []


def test_schedule_scheduled_talks_excludes_no_start(event):
    submission = SubmissionFactory(event=event)
    room = RoomFactory(event=event)
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=None,
        end=None,
        is_visible=True,
    )

    with scope(event=event):
        assert list(schedule.scheduled_talks) == []


def test_schedule_breaks(event):
    room = RoomFactory(event=event)
    with scope(event=event):
        schedule = event.wip_schedule
    break_slot = TalkSlotFactory(
        submission=None,
        schedule=schedule,
        room=room,
        slot_type=SlotType.BREAK,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )
    TalkSlotFactory(
        submission=SubmissionFactory(event=event), schedule=schedule, room=room
    )

    with scope(event=event):
        result = list(schedule.breaks)

    assert result == [break_slot]


def test_schedule_blockers(event):
    room = RoomFactory(event=event)
    with scope(event=event):
        schedule = event.wip_schedule
    blocker = TalkSlotFactory(
        submission=None,
        schedule=schedule,
        room=room,
        slot_type=SlotType.BLOCKER,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )
    TalkSlotFactory(
        submission=SubmissionFactory(event=event), schedule=schedule, room=room
    )

    with scope(event=event):
        result = list(schedule.blockers)

    assert result == [blocker]


def test_schedule_slots_returns_submissions(event):
    """The slots property returns Submission objects, not TalkSlot objects."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    room = RoomFactory(event=event)
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
        is_visible=True,
    )

    result = list(schedule.slots)

    assert result == [submission]


def test_schedule_previous_schedule_none(event):
    with scope(event=event):
        schedule = event.wip_schedule
        assert schedule.previous_schedule is None


def test_schedule_previous_schedule_returns_last_published(event):
    with scope(event=event):
        freeze_schedule(event.wip_schedule, name="v1")
        freeze_schedule(event.wip_schedule, name="v2")
        v2 = Schedule.objects.get(event=event, version="v2")
        v1 = Schedule.objects.get(event=event, version="v1")
        assert v2.previous_schedule == v1


def test_schedule_previous_schedule_wip_returns_latest_published(event):
    with scope(event=event):
        freeze_schedule(event.wip_schedule, name="v1")
        wip = event.wip_schedule
        v1 = Schedule.objects.get(event=event, version="v1")
        assert wip.previous_schedule == v1


def test_schedule_use_room_availabilities_false(event):
    with scope(event=event):
        assert event.wip_schedule.use_room_availabilities is False


def test_schedule_use_room_availabilities_true(event):
    room = RoomFactory(event=event)
    AvailabilityFactory(event=event, room=room)
    with scope(event=event):
        assert event.wip_schedule.use_room_availabilities is True


def test_schedule_changes_create_on_first_release(event):
    with scope(event=event):
        freeze_schedule(event.wip_schedule, name="v1")
        v1 = Schedule.objects.get(event=event, version="v1")

    with scope(event=event):
        assert v1.changes["action"] == "create"


def test_schedule_changes_update_with_new_talk(event):
    room = RoomFactory(event=event)
    with scope(event=event):
        freeze_schedule(event.wip_schedule, name="v1")
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        TalkSlotFactory(submission=submission, room=room)
        freeze_schedule(event.wip_schedule, name="v2")
        v2 = Schedule.objects.get(event=event, version="v2")

        assert v2.changes["action"] == "update"
        assert len(v2.changes["new_talks"]) == 1
        assert v2.changes["new_talks"][0].submission == submission


def test_schedule_changes_canceled_talk(event):
    room = RoomFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    TalkSlotFactory(submission=submission, room=room)
    with scope(event=event):
        freeze_schedule(event.wip_schedule, name="v1")
        wip_slot = event.wip_schedule.talks.get(submission=submission)
        wip_slot.room = None
        wip_slot.start = None
        wip_slot.end = None
        wip_slot.is_visible = False
        wip_slot.save()
        freeze_schedule(event.wip_schedule, name="v2")
        v2 = Schedule.objects.get(event=event, version="v2")

        assert v2.changes["action"] == "update"
        assert len(v2.changes["canceled_talks"]) == 1


def test_schedule_changes_moved_talk(event):
    room = RoomFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    TalkSlotFactory(submission=submission, room=room)
    with scope(event=event):
        freeze_schedule(event.wip_schedule, name="v1")
        wip_slot = event.wip_schedule.talks.get(submission=submission)
        wip_slot.start = event.datetime_from + dt.timedelta(hours=5)
        wip_slot.end = event.datetime_from + dt.timedelta(hours=6)
        wip_slot.save()
        freeze_schedule(event.wip_schedule, name="v2")
        v2 = Schedule.objects.get(event=event, version="v2")

        assert v2.changes["action"] == "update"
        assert len(v2.changes["moved_talks"]) == 1
        assert v2.changes["moved_talks"][0]["submission"] == submission


def test_schedule_unique_event_version():
    event = EventFactory()
    ScheduleFactory(event=event, version="v1")
    with pytest.raises(IntegrityError):
        ScheduleFactory(event=event, version="v1")


def test_schedule_clean_rejects_duplicate_version():
    event = EventFactory()
    ScheduleFactory(event=event, version="v1")
    schedule = Schedule(event=event, version="v1")

    with pytest.raises(ValidationError) as exc_info:
        schedule.clean()
    assert "version" in exc_info.value.message_dict
