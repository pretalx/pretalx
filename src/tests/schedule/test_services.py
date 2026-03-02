# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import json

import pytest
from django.utils.timezone import now
from django_scopes import scope

from pretalx.mail.models import QueuedMail
from pretalx.schedule.models.slot import SlotType
from pretalx.schedule.services import (
    _get_boolean_changes,
    calculate_schedule_changes,
    deserialize_schedule_changes,
    freeze_schedule,
    get_cached_schedule_changes,
    has_unreleased_schedule_changes,
    invalidate_cached_schedule_changes,
    serialize_schedule_changes,
    unfreeze_schedule,
    update_unreleased_schedule_changes,
)
from pretalx.schedule.signals import schedule_release
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    EventFactory,
    RoomFactory,
    ScheduleFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize("change_type", ("new_talks", "canceled_talks"))
def test_serialize_schedule_changes_new_or_canceled_talk(change_type):
    submission = SubmissionFactory()
    slot = TalkSlotFactory(submission=submission)

    changes = {
        "count": 1,
        "action": "update",
        "new_talks": [],
        "canceled_talks": [],
        "moved_talks": [],
    }
    changes[change_type] = [slot]

    result = serialize_schedule_changes(changes)

    assert result["count"] == 1
    assert result["action"] == "update"
    assert len(result[change_type]) == 1
    assert result[change_type][0]["id"] == slot.id
    assert result[change_type][0]["submission_code"] == submission.code
    assert result["moved_talks"] == []


def test_serialize_schedule_changes_moved_talks():
    submission = SubmissionFactory()
    event = submission.event
    room_old = RoomFactory(event=event)
    room_new = RoomFactory(event=event)
    slot = TalkSlotFactory(submission=submission, room=room_new)

    old_start = event.datetime_from
    new_start = event.datetime_from + dt.timedelta(hours=2)
    changes = {
        "count": 1,
        "action": "update",
        "new_talks": [],
        "canceled_talks": [],
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

    result = serialize_schedule_changes(changes)

    assert len(result["moved_talks"]) == 1
    moved = result["moved_talks"][0]
    assert moved["submission_code"] == submission.code
    assert moved["old_start"] == old_start.isoformat()
    assert moved["new_start"] == new_start.isoformat()
    assert moved["old_room"] == room_old.pk
    assert moved["new_room"] == room_new.pk
    assert moved["new_info"] == "Speaker info"
    assert moved["new_slot_id"] == slot.id


def test_serialize_schedule_changes_null_fields():
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

    result = serialize_schedule_changes(changes)

    assert result["new_talks"][0]["submission_code"] is None
    moved = result["moved_talks"][0]
    assert moved["submission_code"] is None
    assert moved["old_start"] is None
    assert moved["new_start"] is None
    assert moved["old_room"] is None
    assert moved["new_room"] is None
    assert moved["new_slot_id"] is None


def test_serialize_schedule_changes_empty():
    changes = {
        "count": 0,
        "action": "update",
        "new_talks": [],
        "canceled_talks": [],
        "moved_talks": [],
    }

    result = serialize_schedule_changes(changes)

    assert result == {
        "count": 0,
        "action": "update",
        "new_talks": [],
        "canceled_talks": [],
        "moved_talks": [],
    }


def test_deserialize_schedule_changes_roundtrip():
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

    serialized = serialize_schedule_changes(original)
    with scope(event=event):
        result = deserialize_schedule_changes(serialized, event)

    assert result["count"] == 3
    assert result["action"] == "update"
    assert len(result["new_talks"]) == 1
    assert result["new_talks"][0].id == new_slot.id
    assert len(result["canceled_talks"]) == 1
    assert result["canceled_talks"][0].id == new_slot.id
    assert len(result["moved_talks"]) == 1
    assert result["moved_talks"][0]["submission"] == submission
    assert result["moved_talks"][0]["old_room"] == room_old
    assert result["moved_talks"][0]["new_room"] == room_new
    assert result["moved_talks"][0]["new_slot"].id == new_slot.id


def test_deserialize_schedule_changes_missing_submission_skips_slot():
    event = EventFactory()

    serialized = {
        "count": 1,
        "action": "update",
        "new_talks": [{"id": 99999, "submission_code": "NONEXIST"}],
        "canceled_talks": [],
        "moved_talks": [],
    }

    with scope(event=event):
        result = deserialize_schedule_changes(serialized, event)

    assert result["new_talks"] == []


def test_deserialize_schedule_changes_missing_slot_skips():
    submission = SubmissionFactory()
    event = submission.event

    serialized = {
        "count": 1,
        "action": "update",
        "new_talks": [{"id": 99999, "submission_code": submission.code}],
        "canceled_talks": [],
        "moved_talks": [],
    }

    with scope(event=event):
        result = deserialize_schedule_changes(serialized, event)

    assert result["new_talks"] == []


def test_deserialize_schedule_changes_moved_without_submission_skipped():
    event = EventFactory()

    serialized = {
        "count": 1,
        "action": "update",
        "new_talks": [],
        "canceled_talks": [],
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
        result = deserialize_schedule_changes(serialized, event)

    assert result["moved_talks"] == []


def test_calculate_schedule_changes_no_previous_schedule(event):
    with scope(event=event):
        result = calculate_schedule_changes(event.wip_schedule)

    assert result["action"] == "create"
    assert result["count"] == 0
    assert result["new_talks"] == []
    assert result["canceled_talks"] == []
    assert result["moved_talks"] == []


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


def test_calculate_schedule_changes_new_talk():
    sub1 = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = sub1.event
    sub2 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    room = RoomFactory(event=event)
    start_time = event.datetime_from
    end_time = start_time + dt.timedelta(hours=1)

    schedule_v1 = ScheduleFactory(
        event=event, version="v1", published=now() - dt.timedelta(hours=2)
    )
    TalkSlotFactory(
        schedule=schedule_v1, submission=sub1, room=room, start=start_time, end=end_time
    )

    schedule_v2 = ScheduleFactory(event=event, version="v2")
    TalkSlotFactory(
        schedule=schedule_v2, submission=sub1, room=room, start=start_time, end=end_time
    )
    TalkSlotFactory(
        schedule=schedule_v2,
        submission=sub2,
        room=room,
        start=start_time + dt.timedelta(hours=2),
        end=end_time + dt.timedelta(hours=2),
    )

    result = calculate_schedule_changes(schedule_v2)

    assert result["action"] == "update"
    assert result["count"] == 1
    assert len(result["new_talks"]) == 1
    assert result["new_talks"][0].submission == sub2


def test_calculate_schedule_changes_canceled_talk():
    sub1 = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = sub1.event
    sub2 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    room = RoomFactory(event=event)
    start_time = event.datetime_from
    end_time = start_time + dt.timedelta(hours=1)

    schedule_v1 = ScheduleFactory(
        event=event, version="v1", published=now() - dt.timedelta(hours=2)
    )
    TalkSlotFactory(
        schedule=schedule_v1, submission=sub1, room=room, start=start_time, end=end_time
    )
    TalkSlotFactory(
        schedule=schedule_v1,
        submission=sub2,
        room=room,
        start=start_time + dt.timedelta(hours=2),
        end=end_time + dt.timedelta(hours=2),
    )

    schedule_v2 = ScheduleFactory(event=event, version="v2")
    TalkSlotFactory(
        schedule=schedule_v2, submission=sub1, room=room, start=start_time, end=end_time
    )

    result = calculate_schedule_changes(schedule_v2)

    assert result["action"] == "update"
    assert result["count"] == 1
    assert len(result["canceled_talks"]) == 1
    assert result["canceled_talks"][0].submission == sub2


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
    assert len(result["new_talks"]) == 1
    assert result["new_talks"][0].submission == sub_new
    assert len(result["canceled_talks"]) == 1
    assert result["canceled_talks"][0].submission == sub_canceled
    assert len(result["moved_talks"]) == 1
    assert result["moved_talks"][0]["submission"] == sub_kept


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
    """When a submission keeps an existing slot and gains an additional one,
    the new slot is detected via the moved_or_new path."""
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
    """When a submission has two slots and both change, the submission is only
    handled once (the second entry hits the 'already handled' guard)."""
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


@pytest.mark.usefixtures("locmem_cache")
def test_invalidate_cached_schedule_changes(event):
    with scope(event=event):
        schedule = event.wip_schedule
        cache_key = f"schedule_{schedule.id}_changes"
        event.cache.set(cache_key, "cached_data")
        assert event.cache.get(cache_key) == "cached_data"

        invalidate_cached_schedule_changes(schedule)

        assert event.cache.get(cache_key) is None


@pytest.mark.usefixtures("locmem_cache")
def test_get_cached_schedule_changes_caches_result(event):
    with scope(event=event):
        schedule = event.wip_schedule
        cache_key = f"schedule_{schedule.id}_changes"

        assert event.cache.get(cache_key) is None

        result = get_cached_schedule_changes(schedule)

        assert result["action"] == "create"
        cached_data = json.loads(event.cache.get(cache_key))
        assert cached_data["action"] == "create"


@pytest.mark.usefixtures("locmem_cache")
def test_get_cached_schedule_changes_uses_cache():
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

    cache_key = f"schedule_{schedule_v2.id}_changes"
    cached = {
        "count": 42,
        "action": "update",
        "new_talks": [],
        "canceled_talks": [],
        "moved_talks": [],
    }
    event.cache.set(cache_key, json.dumps(cached))

    result = get_cached_schedule_changes(schedule_v2)

    assert result["count"] == 42


@pytest.mark.usefixtures("locmem_cache")
def test_get_cached_schedule_changes_invalid_json_recalculates(event):
    with scope(event=event):
        schedule = event.wip_schedule
        cache_key = f"schedule_{schedule.id}_changes"
        event.cache.set(cache_key, "not valid json {{{")

        result = get_cached_schedule_changes(schedule)

        assert result["action"] == "create"


@pytest.mark.usefixtures("locmem_cache")
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


def test_get_boolean_changes_create_action_with_talks():
    submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = submission.event
    TalkSlotFactory(submission=submission)

    changes = {"action": "create", "count": 0}

    result = _get_boolean_changes(event.wip_schedule, changes)

    assert result is True


def test_get_boolean_changes_create_action_without_talks(event):
    changes = {"action": "create", "count": 0}

    result = _get_boolean_changes(event.wip_schedule, changes)

    assert result is False


@pytest.mark.parametrize(("count", "expected"), ((3, True), (0, False)))
def test_get_boolean_changes_update_action(count, expected):
    changes = {"action": "update", "count": count}

    result = _get_boolean_changes(None, changes)

    assert result is expected


@pytest.mark.usefixtures("locmem_cache")
def test_has_unreleased_schedule_changes_returns_cached(event):
    with scope(event=event):
        event.cache.set("has_unreleased_schedule_changes", True)

        assert has_unreleased_schedule_changes(event) is True


@pytest.mark.usefixtures("locmem_cache")
def test_has_unreleased_schedule_changes_calculates_when_not_cached(event):
    with scope(event=event):
        assert event.cache.get("has_unreleased_schedule_changes") is None

        result = has_unreleased_schedule_changes(event)

        assert result is False
        assert event.cache.get("has_unreleased_schedule_changes") is False


@pytest.mark.usefixtures("locmem_cache")
def test_update_unreleased_schedule_changes_with_value(event):
    with scope(event=event):
        update_unreleased_schedule_changes(event, True)

        assert event.cache.get("has_unreleased_schedule_changes") is True


@pytest.mark.usefixtures("locmem_cache")
def test_update_unreleased_schedule_changes_recalculates_when_none(event):
    with scope(event=event):
        event.cache.set("has_unreleased_schedule_changes", True)

        update_unreleased_schedule_changes(event, None)

        assert event.cache.get("has_unreleased_schedule_changes") is False


def test_freeze_schedule_basic():
    submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = submission.event
    room = RoomFactory(event=event)
    wip = event.wip_schedule
    TalkSlotFactory(
        schedule=wip,
        submission=submission,
        room=room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )

    with scope(event=event):
        released, new_wip = freeze_schedule(
            wip, "v1", comment="Release notes", notify_speakers=False
        )

    assert released.version == "v1"
    assert released.comment == "Release notes"
    assert released.published is not None
    assert new_wip.version is None
    assert released.talks.count() == 1
    assert new_wip.talks.count() == 1


@pytest.mark.parametrize(
    ("name", "match"),
    (
        ("wip", "reserved name"),
        ("latest", "reserved name"),
        ("", "without a version name"),
    ),
)
def test_freeze_schedule_rejects_invalid_name(event, name, match):
    with scope(event=event), pytest.raises(ValueError, match=match):
        freeze_schedule(event.wip_schedule, name)


def test_freeze_schedule_rejects_already_frozen():
    event = EventFactory()
    wip = event.wip_schedule
    released, _ = freeze_schedule(wip, "v1", notify_speakers=False)

    with pytest.raises(ValueError, match="already versioned"):
        freeze_schedule(released, "v2")


def test_freeze_schedule_sets_visibility_for_confirmed_and_breaks():
    confirmed = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = confirmed.event
    unconfirmed = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    room = RoomFactory(event=event)
    wip = event.wip_schedule
    start = event.datetime_from
    end = start + dt.timedelta(hours=1)

    TalkSlotFactory(schedule=wip, submission=confirmed, room=room, start=start, end=end)
    TalkSlotFactory(
        schedule=wip,
        submission=unconfirmed,
        room=room,
        start=start + dt.timedelta(hours=2),
        end=end + dt.timedelta(hours=2),
    )
    TalkSlotFactory(
        submission=None,
        schedule=wip,
        room=room,
        start=start + dt.timedelta(hours=4),
        end=end + dt.timedelta(hours=4),
        is_visible=False,
        slot_type=SlotType.BREAK,
        description="Coffee Break",
    )

    with scope(event=event):
        released, _ = freeze_schedule(wip, "v1", notify_speakers=False)

    confirmed_slot = released.talks.get(submission=confirmed)
    unconfirmed_slot = released.talks.get(submission=unconfirmed)
    break_slot = released.talks.get(slot_type=SlotType.BREAK)

    assert confirmed_slot.is_visible is True
    assert unconfirmed_slot.is_visible is False
    assert break_slot.is_visible is True


def test_freeze_schedule_removes_blockers_from_released():
    event = EventFactory()
    room = RoomFactory(event=event)
    wip = event.wip_schedule
    start = event.datetime_from

    TalkSlotFactory(
        submission=None,
        schedule=wip,
        room=room,
        start=start,
        end=start + dt.timedelta(hours=1),
        slot_type=SlotType.BLOCKER,
        description="Blocked",
    )

    with scope(event=event):
        released, new_wip = freeze_schedule(wip, "v1", notify_speakers=False)

    assert released.talks.filter(slot_type=SlotType.BLOCKER).count() == 0
    assert new_wip.talks.filter(slot_type=SlotType.BLOCKER).count() == 1


def test_freeze_schedule_fires_signal(event, register_signal_handler):
    received = []

    def handler(signal, sender, **kwargs):
        received.append(kwargs)

    register_signal_handler(schedule_release, handler)

    with scope(event=event):
        released, _ = freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    assert len(received) == 1
    assert received[0]["schedule"] == released


def test_freeze_schedule_invalidates_wip_cache():
    event = EventFactory()
    old_wip = event.wip_schedule
    freeze_schedule(old_wip, "v1", notify_speakers=False)

    assert event.wip_schedule.version is None
    assert event.wip_schedule.pk != old_wip.pk


@pytest.mark.usefixtures("locmem_cache")
def test_freeze_schedule_clears_unreleased_changes_flag():
    event = EventFactory()
    event.cache.set("has_unreleased_schedule_changes", True)
    freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    assert event.cache.get("has_unreleased_schedule_changes") is False


def test_freeze_schedule_with_notify_speakers():
    submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = submission.event
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    room = RoomFactory(event=event)
    wip = event.wip_schedule
    TalkSlotFactory(
        schedule=wip,
        submission=submission,
        room=room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )

    with scope(event=event):
        released, _ = freeze_schedule(wip, "v1", notify_speakers=True)

    assert QueuedMail.objects.filter(to_users=speaker.user).count() == 1


def test_unfreeze_schedule_basic():
    submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = submission.event
    room = RoomFactory(event=event)
    start = event.datetime_from
    end = start + dt.timedelta(hours=1)

    TalkSlotFactory(
        schedule=event.wip_schedule,
        submission=submission,
        room=room,
        start=start,
        end=end,
    )
    released_v1, _ = freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    # Modify WIP: remove the slot
    wip = event.wip_schedule
    wip.talks.all().update(room=None, start=None, end=None)
    _, _ = freeze_schedule(wip, "v2", notify_speakers=False)

    # Unfreeze to v1
    _, new_wip = unfreeze_schedule(released_v1)

    assert new_wip.version is None
    assert new_wip.talks.filter(submission=submission).count() == 1


def test_unfreeze_schedule_rejects_wip(event):
    with scope(event=event), pytest.raises(ValueError, match="not released yet"):
        unfreeze_schedule(event.wip_schedule)


def test_unfreeze_schedule_preserves_talks_from_both_versions():
    """Unfreezing merges talks from the old version and the current WIP
    (the bug72 scenario: talks added after v1 are preserved)."""
    sub1 = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = sub1.event
    room = RoomFactory(event=event)
    start = event.datetime_from
    end = start + dt.timedelta(hours=1)

    TalkSlotFactory(
        schedule=event.wip_schedule, submission=sub1, room=room, start=start, end=end
    )
    released_v1, _ = freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    # Add a second submission to the WIP
    sub2 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    wip = event.wip_schedule
    TalkSlotFactory(
        schedule=wip,
        submission=sub2,
        room=room,
        start=start + dt.timedelta(hours=2),
        end=end + dt.timedelta(hours=2),
    )
    freeze_schedule(wip, "v2", notify_speakers=False)

    # Unfreeze to v1 — should still have sub2's slot from the WIP
    _, new_wip = unfreeze_schedule(released_v1)

    assert new_wip.talks.count() == 2
    submission_ids = set(new_wip.talks.values_list("submission_id", flat=True))
    assert submission_ids == {sub1.pk, sub2.pk}


@pytest.mark.usefixtures("locmem_cache")
def test_unfreeze_schedule_clears_unreleased_changes_flag():
    event = EventFactory()
    released, _ = freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
    event.cache.set("has_unreleased_schedule_changes", True)

    unfreeze_schedule(released)

    assert event.cache.get("has_unreleased_schedule_changes") is False


def test_deserialize_schedule_changes_canceled_missing_slot_skips():
    submission = SubmissionFactory()
    event = submission.event

    serialized = {
        "count": 1,
        "action": "update",
        "new_talks": [],
        "canceled_talks": [{"id": 99999, "submission_code": submission.code}],
        "moved_talks": [],
    }

    with scope(event=event):
        result = deserialize_schedule_changes(serialized, event)

    assert result["canceled_talks"] == []


def test_deserialize_schedule_changes_null_submission_codes():
    event = EventFactory()
    slot = TalkSlotFactory(
        submission=None, schedule=event.wip_schedule, room=None, is_visible=False
    )

    serialized = {
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

    with scope(event=event):
        result = deserialize_schedule_changes(serialized, event)

    assert len(result["new_talks"]) == 1
    assert result["new_talks"][0].id == slot.id
    assert result["moved_talks"] == []


def test_deserialize_schedule_changes_slot_exists_no_matching_submission():
    """When a slot exists but its submission_code has no match, the slot is
    still appended (without overwriting its submission)."""
    submission = SubmissionFactory()
    event = submission.event
    slot = TalkSlotFactory(submission=submission)

    serialized = {
        "count": 1,
        "action": "update",
        "new_talks": [{"id": slot.id, "submission_code": "XXXXXX"}],
        "canceled_talks": [{"id": slot.id, "submission_code": "XXXXXX"}],
        "moved_talks": [],
    }

    with scope(event=event):
        result = deserialize_schedule_changes(serialized, event)

    assert len(result["new_talks"]) == 1
    assert result["new_talks"][0].id == slot.id
    assert len(result["canceled_talks"]) == 1


def test_deserialize_schedule_changes_moved_with_null_rooms():
    submission = SubmissionFactory()
    event = submission.event
    slot = TalkSlotFactory(submission=submission)

    start_iso = event.datetime_from.isoformat()
    serialized = {
        "count": 1,
        "action": "update",
        "new_talks": [],
        "canceled_talks": [],
        "moved_talks": [
            {
                "submission_code": submission.code,
                "old_start": start_iso,
                "new_start": start_iso,
                "old_room": None,
                "new_room": None,
                "new_info": "",
                "new_slot_id": slot.id,
            }
        ],
    }

    with scope(event=event):
        result = deserialize_schedule_changes(serialized, event)

    assert len(result["moved_talks"]) == 1
    assert result["moved_talks"][0]["old_room"] is None
    assert result["moved_talks"][0]["new_room"] is None
