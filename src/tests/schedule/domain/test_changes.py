# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import json

import pytest
from django.utils.timezone import now
from django_scopes import scope

from pretalx.schedule.domain.changes import (
    _deserialize_changes,
    _get_boolean_changes,
    _serialize_changes,
    calculate_schedule_changes,
    get_cached_schedule_changes,
    has_unreleased_schedule_changes,
    invalidate_cached_schedule_changes,
    update_unreleased_schedule_changes,
)
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    EventFactory,
    RoomFactory,
    ScheduleFactory,
    SubmissionFactory,
    TalkSlotFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

EMPTY_CHANGES = {
    "count": 0,
    "action": "update",
    "new_talks": [],
    "canceled_talks": [],
    "moved_talks": [],
}


def test_serialize_changes_flattens_slots_rooms_and_times():
    submission = SubmissionFactory()
    event = submission.event
    room_old = RoomFactory(event=event)
    room_new = RoomFactory(event=event)
    slot = TalkSlotFactory(submission=submission, room=room_new)
    old_start = event.datetime_from
    new_start = event.datetime_from + dt.timedelta(hours=2)
    changes = {
        "count": 3,
        "action": "update",
        "new_talks": [slot],
        "canceled_talks": [slot],
        "moved_talks": [
            {
                "submission": submission,
                "old_start": old_start,
                "new_start": new_start,
                "old_room": room_old,
                "new_room": room_new,
                "new_info": "Speaker info",
                "new_slot": slot,
            }
        ],
    }

    assert _serialize_changes(EMPTY_CHANGES) == EMPTY_CHANGES
    assert _serialize_changes(changes) == {
        "count": 3,
        "action": "update",
        "new_talks": [{"id": slot.id, "submission_code": submission.code}],
        "canceled_talks": [{"id": slot.id, "submission_code": submission.code}],
        "moved_talks": [
            {
                "submission_code": submission.code,
                "old_start": old_start.isoformat(),
                "new_start": new_start.isoformat(),
                "old_room": room_old.pk,
                "new_room": room_new.pk,
                "new_info": "Speaker info",
                "new_slot_id": slot.id,
            }
        ],
    }


def test_serialize_changes_null_fields():
    event = EventFactory()
    slot = TalkSlotFactory(
        submission=None, schedule=event.wip_schedule, room=None, is_visible=False
    )
    changes = {
        "count": 1,
        "action": "update",
        "new_talks": [slot],
        "canceled_talks": [],
        "moved_talks": [
            {
                "submission": None,
                "old_start": None,
                "new_start": None,
                "old_room": None,
                "new_room": None,
                "new_info": "",
                "new_slot": None,
            }
        ],
    }

    assert _serialize_changes(changes) == {
        "count": 1,
        "action": "update",
        "new_talks": [{"id": slot.id, "submission_code": None}],
        "canceled_talks": [],
        "moved_talks": [
            {
                "submission_code": None,
                "old_start": None,
                "new_start": None,
                "old_room": None,
                "new_room": None,
                "new_info": "",
                "new_slot_id": None,
            }
        ],
    }


def test_deserialize_changes_roundtrip():
    submission = SubmissionFactory()
    event = submission.event
    room_old = RoomFactory(event=event)
    room_new = RoomFactory(event=event)
    new_slot = TalkSlotFactory(submission=submission, room=room_new)

    old_start = event.datetime_from
    new_start = event.datetime_from + dt.timedelta(hours=2)
    original = {
        "count": 3,
        "action": "update",
        "new_talks": [new_slot],
        "canceled_talks": [new_slot],
        "moved_talks": [
            {
                "submission": submission,
                "old_start": old_start,
                "new_start": new_start,
                "old_room": room_old,
                "new_room": room_new,
                "new_info": "Info",
                "new_slot": new_slot,
            }
        ],
    }

    serialized = _serialize_changes(original)
    with scope(event=event):
        result = _deserialize_changes(serialized, event)

    assert result["count"] == 3
    assert result["action"] == "update"
    assert [slot.id for slot in result["new_talks"]] == [new_slot.id]
    assert [slot.id for slot in result["canceled_talks"]] == [new_slot.id]
    assert len(result["moved_talks"]) == 1
    assert result["moved_talks"][0]["submission"] == submission
    assert result["moved_talks"][0]["old_room"] == room_old
    assert result["moved_talks"][0]["new_room"] == room_new
    assert result["moved_talks"][0]["new_slot"].id == new_slot.id


def test_deserialize_changes_skips_unknown_submissions_and_slots():
    submission = SubmissionFactory()
    event = submission.event
    serialized = {
        "count": 3,
        "action": "update",
        "new_talks": [
            {"id": 99999, "submission_code": "NONEXIST"},
            {"id": 99999, "submission_code": submission.code},
        ],
        "canceled_talks": [{"id": 99999, "submission_code": submission.code}],
        "moved_talks": [
            {
                "submission_code": "NOSUCH",
                "old_start": None,
                "new_start": None,
                "old_room": None,
                "new_room": None,
                "new_info": "",
                "new_slot_id": None,
            }
        ],
    }

    with scope(event=event):
        result = _deserialize_changes(serialized, event)

    assert result == {
        "count": 3,
        "action": "update",
        "new_talks": [],
        "canceled_talks": [],
        "moved_talks": [],
    }


def test_deserialize_changes_looks_slots_up_by_id_and_tolerates_null_fields():
    submission = SubmissionFactory()
    event = submission.event
    slot = TalkSlotFactory(submission=submission)
    bare_slot = TalkSlotFactory(
        submission=None, schedule=event.wip_schedule, room=None, is_visible=False
    )
    start_iso = event.datetime_from.isoformat()
    serialized = {
        "count": 1,
        "action": "update",
        "new_talks": [
            {"id": bare_slot.id, "submission_code": None},
            {"id": slot.id, "submission_code": "XXXXXX"},
        ],
        "canceled_talks": [{"id": slot.id, "submission_code": "XXXXXX"}],
        "moved_talks": [
            {
                "submission_code": None,
                "old_start": None,
                "new_start": None,
                "old_room": None,
                "new_room": None,
                "new_info": "",
                "new_slot_id": None,
            },
            {
                "submission_code": submission.code,
                "old_start": start_iso,
                "new_start": start_iso,
                "old_room": None,
                "new_room": None,
                "new_info": "",
                "new_slot_id": slot.id,
            },
        ],
    }

    with scope(event=event):
        result = _deserialize_changes(serialized, event)

    assert [talk.id for talk in result["new_talks"]] == [bare_slot.id, slot.id]
    assert [talk.id for talk in result["canceled_talks"]] == [slot.id]
    assert len(result["moved_talks"]) == 1
    assert result["moved_talks"][0]["submission"] == submission
    assert result["moved_talks"][0]["old_room"] is None
    assert result["moved_talks"][0]["new_room"] is None


def test_calculate_schedule_changes_no_previous_schedule(event):
    with scope(event=event):
        result = calculate_schedule_changes(event.wip_schedule)

    assert result == {
        "action": "create",
        "count": 0,
        "new_talks": [],
        "canceled_talks": [],
        "moved_talks": [],
    }


def test_calculate_schedule_changes_no_changes():
    submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = submission.event
    room = RoomFactory(event=event)
    start_time = event.datetime_from
    end_time = start_time + dt.timedelta(hours=1)

    schedule_v1 = ScheduleFactory(
        event=event, version="v1", published=now() - dt.timedelta(hours=2)
    )
    TalkSlotFactory(
        schedule=schedule_v1,
        submission=submission,
        room=room,
        start=start_time,
        end=end_time,
    )

    schedule_v2 = ScheduleFactory(event=event, version="v2")
    TalkSlotFactory(
        schedule=schedule_v2,
        submission=submission,
        room=room,
        start=start_time,
        end=end_time,
    )

    result = calculate_schedule_changes(schedule_v2)

    assert result["action"] == "update"
    assert result["count"] == 0


def test_calculate_schedule_changes_moved_talk_room_change():
    submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = submission.event
    room1 = RoomFactory(event=event)
    room2 = RoomFactory(event=event)
    start_time = event.datetime_from
    end_time = start_time + dt.timedelta(hours=1)

    schedule_v1 = ScheduleFactory(
        event=event, version="v1", published=now() - dt.timedelta(hours=2)
    )
    TalkSlotFactory(
        schedule=schedule_v1,
        submission=submission,
        room=room1,
        start=start_time,
        end=end_time,
    )

    schedule_v2 = ScheduleFactory(event=event, version="v2")
    TalkSlotFactory(
        schedule=schedule_v2,
        submission=submission,
        room=room2,
        start=start_time,
        end=end_time,
    )

    result = calculate_schedule_changes(schedule_v2)

    assert result["action"] == "update"
    assert result["count"] == 1
    assert len(result["moved_talks"]) == 1
    assert result["moved_talks"][0]["submission"] == submission
    assert result["moved_talks"][0]["old_room"] == room1
    assert result["moved_talks"][0]["new_room"] == room2


def test_calculate_schedule_changes_moved_talk_time_change():
    submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = submission.event
    room = RoomFactory(event=event)
    start_time = event.datetime_from
    end_time = start_time + dt.timedelta(hours=1)
    new_start = start_time + dt.timedelta(hours=3)
    new_end = end_time + dt.timedelta(hours=3)

    schedule_v1 = ScheduleFactory(
        event=event, version="v1", published=now() - dt.timedelta(hours=2)
    )
    TalkSlotFactory(
        schedule=schedule_v1,
        submission=submission,
        room=room,
        start=start_time,
        end=end_time,
    )

    schedule_v2 = ScheduleFactory(event=event, version="v2")
    TalkSlotFactory(
        schedule=schedule_v2,
        submission=submission,
        room=room,
        start=new_start,
        end=new_end,
    )

    result = calculate_schedule_changes(schedule_v2)

    assert result["action"] == "update"
    assert result["count"] == 1
    assert len(result["moved_talks"]) == 1
    assert result["moved_talks"][0]["old_start"] == start_time.astimezone(event.tz)
    assert result["moved_talks"][0]["new_start"] == new_start.astimezone(event.tz)


def test_calculate_schedule_changes_mixed():
    sub_kept = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = sub_kept.event
    sub_new = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    sub_canceled = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    room1 = RoomFactory(event=event)
    room2 = RoomFactory(event=event)
    start_time = event.datetime_from
    end_time = start_time + dt.timedelta(hours=1)

    schedule_v1 = ScheduleFactory(
        event=event, version="v1", published=now() - dt.timedelta(hours=2)
    )
    TalkSlotFactory(
        schedule=schedule_v1,
        submission=sub_kept,
        room=room1,
        start=start_time,
        end=end_time,
    )
    TalkSlotFactory(
        schedule=schedule_v1,
        submission=sub_canceled,
        room=room1,
        start=start_time + dt.timedelta(hours=2),
        end=end_time + dt.timedelta(hours=2),
    )

    schedule_v2 = ScheduleFactory(event=event, version="v2")
    TalkSlotFactory(
        schedule=schedule_v2,
        submission=sub_kept,
        room=room2,
        start=start_time,
        end=end_time,
    )
    TalkSlotFactory(
        schedule=schedule_v2,
        submission=sub_new,
        room=room1,
        start=start_time + dt.timedelta(hours=4),
        end=end_time + dt.timedelta(hours=4),
    )

    result = calculate_schedule_changes(schedule_v2)

    assert result["action"] == "update"
    assert result["count"] == 3
    assert [slot.submission for slot in result["new_talks"]] == [sub_new]
    assert [slot.submission for slot in result["canceled_talks"]] == [sub_canceled]
    assert [moved["submission"] for moved in result["moved_talks"]] == [sub_kept]


def test_calculate_schedule_changes_submission_loses_slot():
    submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = submission.event
    room = RoomFactory(event=event)
    start = event.datetime_from
    end = start + dt.timedelta(hours=1)

    schedule_v1 = ScheduleFactory(
        event=event, version="v1", published=now() - dt.timedelta(hours=2)
    )
    TalkSlotFactory(
        schedule=schedule_v1, submission=submission, room=room, start=start, end=end
    )
    TalkSlotFactory(
        schedule=schedule_v1,
        submission=submission,
        room=room,
        start=start + dt.timedelta(hours=3),
        end=end + dt.timedelta(hours=3),
    )

    schedule_v2 = ScheduleFactory(event=event, version="v2")
    TalkSlotFactory(
        schedule=schedule_v2, submission=submission, room=room, start=start, end=end
    )

    result = calculate_schedule_changes(schedule_v2)

    assert result["count"] == 1
    assert len(result["canceled_talks"]) == 1
    assert result["canceled_talks"][0].submission == submission


def test_calculate_schedule_changes_submission_gains_slot():
    submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = submission.event
    room = RoomFactory(event=event)
    start = event.datetime_from
    end = start + dt.timedelta(hours=1)

    schedule_v1 = ScheduleFactory(
        event=event, version="v1", published=now() - dt.timedelta(hours=2)
    )
    TalkSlotFactory(
        schedule=schedule_v1, submission=submission, room=room, start=start, end=end
    )

    schedule_v2 = ScheduleFactory(event=event, version="v2")
    TalkSlotFactory(
        schedule=schedule_v2, submission=submission, room=room, start=start, end=end
    )
    TalkSlotFactory(
        schedule=schedule_v2,
        submission=submission,
        room=room,
        start=start + dt.timedelta(hours=3),
        end=end + dt.timedelta(hours=3),
    )

    result = calculate_schedule_changes(schedule_v2)

    assert result["count"] == 1
    assert len(result["new_talks"]) == 1
    assert result["new_talks"][0].submission == submission


def test_calculate_schedule_changes_multi_slot_submission_both_moved():
    submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = submission.event
    room1 = RoomFactory(event=event)
    room2 = RoomFactory(event=event)
    start = event.datetime_from
    end = start + dt.timedelta(hours=1)

    schedule_v1 = ScheduleFactory(
        event=event, version="v1", published=now() - dt.timedelta(hours=2)
    )
    TalkSlotFactory(
        schedule=schedule_v1, submission=submission, room=room1, start=start, end=end
    )
    TalkSlotFactory(
        schedule=schedule_v1,
        submission=submission,
        room=room2,
        start=start + dt.timedelta(hours=3),
        end=end + dt.timedelta(hours=3),
    )

    schedule_v2 = ScheduleFactory(event=event, version="v2")
    TalkSlotFactory(
        schedule=schedule_v2,
        submission=submission,
        room=room1,
        start=start + dt.timedelta(hours=1),
        end=end + dt.timedelta(hours=1),
    )
    TalkSlotFactory(
        schedule=schedule_v2,
        submission=submission,
        room=room2,
        start=start + dt.timedelta(hours=4),
        end=end + dt.timedelta(hours=4),
    )

    result = calculate_schedule_changes(schedule_v2)

    assert result["count"] == 2
    assert len(result["moved_talks"]) == 2


def test_get_cached_schedule_changes_caches_invalidates_and_survives_bad_cache(event):
    with scope(event=event):
        schedule = event.wip_schedule
        cache_key = f"schedule_{schedule.id}_changes"
        assert event.cache.get(cache_key) is None

        result = get_cached_schedule_changes(schedule)

        assert result["action"] == "create"
        assert json.loads(event.cache.get(cache_key))["action"] == "create"

        event.cache.set(cache_key, json.dumps(EMPTY_CHANGES | {"count": 42}))
        assert get_cached_schedule_changes(schedule)["count"] == 42

        invalidate_cached_schedule_changes(schedule)
        assert event.cache.get(cache_key) is None

        event.cache.set(cache_key, "not valid json {{{")
        assert get_cached_schedule_changes(schedule)["action"] == "create"


def test_get_cached_schedule_changes_versioned_schedule():
    sub = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = sub.event
    room = RoomFactory(event=event)
    start = event.datetime_from
    end = start + dt.timedelta(hours=1)

    schedule_v1 = ScheduleFactory(
        event=event, version="v1", published=now() - dt.timedelta(hours=2)
    )
    TalkSlotFactory(
        schedule=schedule_v1, submission=sub, room=room, start=start, end=end
    )

    schedule_v2 = ScheduleFactory(event=event, version="v2")
    TalkSlotFactory(
        schedule=schedule_v2, submission=sub, room=room, start=start, end=end
    )

    result = get_cached_schedule_changes(schedule_v2)

    assert result["action"] == "update"
    assert result["count"] == 0


def test_get_boolean_changes_create_action_depends_on_scheduled_talks(event):
    changes = {"action": "create", "count": 0}

    assert _get_boolean_changes(event.wip_schedule, changes) is False

    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    TalkSlotFactory(submission=submission, schedule=event.wip_schedule)

    assert _get_boolean_changes(event.wip_schedule, changes) is True


@pytest.mark.parametrize(("count", "expected"), ((3, True), (0, False)))
def test_get_boolean_changes_update_action(count, expected):
    changes = {"action": "update", "count": count}

    result = _get_boolean_changes(None, changes)

    assert result is expected


def test_unreleased_schedule_changes_cache_round_trip(event):
    cache_key = "has_unreleased_schedule_changes"
    with scope(event=event):
        assert event.cache.get(cache_key) is None

        assert has_unreleased_schedule_changes(event) is False
        assert event.cache.get(cache_key) is False

        update_unreleased_schedule_changes(event, True)
        assert event.cache.get(cache_key) is True
        assert has_unreleased_schedule_changes(event) is True

        update_unreleased_schedule_changes(event, None)
        assert event.cache.get(cache_key) is False
