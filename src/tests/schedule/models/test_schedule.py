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
    ("version", "fallback", "url_version"),
    (
        (None, "wip", "wip"),
        ("v1", "v1", "v1"),
        ("version 1", "version 1", "version%201"),
    ),
    ids=["wip", "plain", "encoded"],
)
def test_schedule_version_properties(version, fallback, url_version):
    schedule = ScheduleFactory(version=version)

    assert (schedule.version_with_fallback, schedule.url_version) == (
        fallback,
        url_version,
    )


def test_schedule_release_chain_tracks_previous_schedule_and_changes(event):
    room = RoomFactory(event=event)
    moved = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    canceled = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    added = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    TalkSlotFactory(submission=moved, room=room)
    TalkSlotFactory(submission=canceled, room=room)

    with scope(event=event):
        wip = event.wip_schedule
        assert (wip.is_archived, wip.previous_schedule) == (False, None)

        freeze_schedule(wip, name="v1")
        v1 = Schedule.objects.select_related("event").get(event=event, version="v1")
        assert (v1.is_archived, v1.previous_schedule, v1.changes["action"]) == (
            False,
            None,
            "create",
        )
        assert event.wip_schedule.previous_schedule == v1

        moved_slot = event.wip_schedule.talks.get(submission=moved)
        moved_slot.start = event.datetime_from + dt.timedelta(hours=5)
        moved_slot.end = event.datetime_from + dt.timedelta(hours=6)
        moved_slot.save()
        canceled_slot = event.wip_schedule.talks.get(submission=canceled)
        canceled_slot.room = None
        canceled_slot.start = None
        canceled_slot.end = None
        canceled_slot.is_visible = False
        canceled_slot.save()
        TalkSlotFactory(submission=added, room=room)
        freeze_schedule(event.wip_schedule, name="v2")
        v1 = Schedule.objects.select_related("event").get(event=event, version="v1")
        v2 = Schedule.objects.select_related("event").get(event=event, version="v2")

        assert (v1.is_archived, v2.is_archived, v2.previous_schedule) == (
            True,
            False,
            v1,
        )
        assert v2.changes["action"] == "update"
        assert [slot.submission for slot in v2.changes["new_talks"]] == [added]
        assert [slot.submission for slot in v2.changes["canceled_talks"]] == [canceled]
        assert [move["submission"] for move in v2.changes["moved_talks"]] == [moved]


def test_schedule_slot_collections(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    room = RoomFactory(event=event)
    start = event.datetime_from
    end = start + dt.timedelta(hours=1)
    with scope(event=event):
        schedule = event.wip_schedule
    visible = TalkSlotFactory(
        submission=submission, schedule=schedule, room=room, start=start, end=end
    )
    TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=start,
        end=end,
        is_visible=False,
    )
    TalkSlotFactory(
        submission=submission, schedule=schedule, room=None, start=start, end=end
    )
    TalkSlotFactory(
        submission=submission, schedule=schedule, room=room, start=None, end=None
    )
    break_slot = TalkSlotFactory(
        submission=None,
        schedule=schedule,
        room=room,
        slot_type=SlotType.BREAK,
        start=start,
        end=end,
    )
    blocker = TalkSlotFactory(
        submission=None,
        schedule=schedule,
        room=room,
        slot_type=SlotType.BLOCKER,
        start=start,
        end=end,
    )

    with scope(event=event):
        assert list(schedule.scheduled_talks) == [visible]
        assert list(schedule.breaks) == [break_slot]
        assert list(schedule.blockers) == [blocker]
        assert list(schedule.slots) == [submission]


def test_schedule_use_room_availabilities(event):
    with scope(event=event):
        without = event.wip_schedule.use_room_availabilities
        AvailabilityFactory(event=event, room=RoomFactory(event=event))
        del event.wip_schedule.__dict__["use_room_availabilities"]
        with_avails = event.wip_schedule.use_room_availabilities

    assert (without, with_avails) == (False, True)


def test_schedule_version_unique_per_event():
    event = EventFactory()
    ScheduleFactory(event=event, version="v1")

    with pytest.raises(ValidationError) as exc_info:
        Schedule(event=event, version="v1").clean()
    assert exc_info.value.message_dict == {
        "version": [
            "This schedule version was used already, please choose a different one."
        ]
    }
    with pytest.raises(IntegrityError):
        ScheduleFactory(event=event, version="v1")
