import datetime as dt
import json

import pytest
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

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

pytestmark = pytest.mark.unit


@pytest.mark.django_db
@pytest.mark.parametrize("change_type", ("new_talks", "canceled_talks"))
def test_serialize_schedule_changes_new_or_canceled_talk(change_type):
    with scopes_disabled():
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


@pytest.mark.django_db
def test_serialize_schedule_changes_moved_talks():
    with scopes_disabled():
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


@pytest.mark.django_db
def test_serialize_schedule_changes_null_fields():
    """Serialization handles None submission, room, start gracefully."""
    with scopes_disabled():
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


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_deserialize_schedule_changes_roundtrip():
    """Serialize then deserialize produces equivalent changes."""
    with scopes_disabled():
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


@pytest.mark.django_db
def test_deserialize_schedule_changes_missing_submission_skips_slot():
    """Slots referencing nonexistent submissions are silently skipped."""
    with scopes_disabled():
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


@pytest.mark.django_db
def test_deserialize_schedule_changes_missing_slot_skips():
    """Entries referencing nonexistent slot IDs are silently skipped."""
    with scopes_disabled():
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


@pytest.mark.django_db
def test_deserialize_schedule_changes_moved_without_submission_skipped():
    """Moved talks referencing a missing submission are skipped entirely."""
    with scopes_disabled():
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


@pytest.mark.django_db
def test_calculate_schedule_changes_no_previous_schedule(event):
    """First schedule returns action='create' with no change details."""
    with scope(event=event):
        result = calculate_schedule_changes(event.wip_schedule)

    assert result["action"] == "create"
    assert result["count"] == 0
    assert result["new_talks"] == []
    assert result["canceled_talks"] == []
    assert result["moved_talks"] == []


@pytest.mark.django_db
def test_calculate_schedule_changes_no_changes():
    """Identical schedules produce count=0."""
    with scopes_disabled():
        submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
        event = submission.event
        room = RoomFactory(event=event)
        start_time = event.datetime_from
        end_time = start_time + dt.timedelta(hours=1)

        schedule_v1 = event.wip_schedule
        TalkSlotFactory(
            schedule=schedule_v1,
            submission=submission,
            room=room,
            start=start_time,
            end=end_time,
        )
        schedule_v1.version = "v1"
        schedule_v1.published = now() - dt.timedelta(hours=2)
        schedule_v1.save()

        schedule_v2 = ScheduleFactory(event=event)
        TalkSlotFactory(
            schedule=schedule_v2,
            submission=submission,
            room=room,
            start=start_time,
            end=end_time,
        )
        schedule_v2.version = "v2"
        schedule_v2.published = now()
        schedule_v2.save()

    with scopes_disabled():
        result = calculate_schedule_changes(schedule_v2)

    assert result["action"] == "update"
    assert result["count"] == 0


@pytest.mark.django_db
def test_calculate_schedule_changes_new_talk():
    """A talk present in the new schedule but not the old is detected as new."""
    with scopes_disabled():
        sub1 = SubmissionFactory(state=SubmissionStates.CONFIRMED)
        event = sub1.event
        sub2 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        room = RoomFactory(event=event)
        start_time = event.datetime_from
        end_time = start_time + dt.timedelta(hours=1)

        schedule_v1 = event.wip_schedule
        TalkSlotFactory(
            schedule=schedule_v1,
            submission=sub1,
            room=room,
            start=start_time,
            end=end_time,
        )
        schedule_v1.version = "v1"
        schedule_v1.published = now() - dt.timedelta(hours=2)
        schedule_v1.save()

        schedule_v2 = ScheduleFactory(event=event)
        TalkSlotFactory(
            schedule=schedule_v2,
            submission=sub1,
            room=room,
            start=start_time,
            end=end_time,
        )
        TalkSlotFactory(
            schedule=schedule_v2,
            submission=sub2,
            room=room,
            start=start_time + dt.timedelta(hours=2),
            end=end_time + dt.timedelta(hours=2),
        )
        schedule_v2.version = "v2"
        schedule_v2.published = now()
        schedule_v2.save()

    with scopes_disabled():
        result = calculate_schedule_changes(schedule_v2)

    assert result["action"] == "update"
    assert result["count"] == 1
    assert len(result["new_talks"]) == 1
    assert result["new_talks"][0].submission == sub2


@pytest.mark.django_db
def test_calculate_schedule_changes_canceled_talk():
    """A talk present in the old schedule but not the new is detected as canceled."""
    with scopes_disabled():
        sub1 = SubmissionFactory(state=SubmissionStates.CONFIRMED)
        event = sub1.event
        sub2 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        room = RoomFactory(event=event)
        start_time = event.datetime_from
        end_time = start_time + dt.timedelta(hours=1)

        schedule_v1 = event.wip_schedule
        TalkSlotFactory(
            schedule=schedule_v1,
            submission=sub1,
            room=room,
            start=start_time,
            end=end_time,
        )
        TalkSlotFactory(
            schedule=schedule_v1,
            submission=sub2,
            room=room,
            start=start_time + dt.timedelta(hours=2),
            end=end_time + dt.timedelta(hours=2),
        )
        schedule_v1.version = "v1"
        schedule_v1.published = now() - dt.timedelta(hours=2)
        schedule_v1.save()

        schedule_v2 = ScheduleFactory(event=event)
        TalkSlotFactory(
            schedule=schedule_v2,
            submission=sub1,
            room=room,
            start=start_time,
            end=end_time,
        )
        schedule_v2.version = "v2"
        schedule_v2.published = now()
        schedule_v2.save()

    with scopes_disabled():
        result = calculate_schedule_changes(schedule_v2)

    assert result["action"] == "update"
    assert result["count"] == 1
    assert len(result["canceled_talks"]) == 1
    assert result["canceled_talks"][0].submission == sub2


@pytest.mark.django_db
def test_calculate_schedule_changes_moved_talk_room_change():
    """A talk moved to a different room is detected as moved."""
    with scopes_disabled():
        submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
        event = submission.event
        room1 = RoomFactory(event=event)
        room2 = RoomFactory(event=event)
        start_time = event.datetime_from
        end_time = start_time + dt.timedelta(hours=1)

        schedule_v1 = event.wip_schedule
        TalkSlotFactory(
            schedule=schedule_v1,
            submission=submission,
            room=room1,
            start=start_time,
            end=end_time,
        )
        schedule_v1.version = "v1"
        schedule_v1.published = now() - dt.timedelta(hours=2)
        schedule_v1.save()

        schedule_v2 = ScheduleFactory(event=event)
        TalkSlotFactory(
            schedule=schedule_v2,
            submission=submission,
            room=room2,
            start=start_time,
            end=end_time,
        )
        schedule_v2.version = "v2"
        schedule_v2.published = now()
        schedule_v2.save()

    with scopes_disabled():
        result = calculate_schedule_changes(schedule_v2)

    assert result["action"] == "update"
    assert result["count"] == 1
    assert len(result["moved_talks"]) == 1
    assert result["moved_talks"][0]["submission"] == submission
    assert result["moved_talks"][0]["old_room"] == room1
    assert result["moved_talks"][0]["new_room"] == room2


@pytest.mark.django_db
def test_calculate_schedule_changes_moved_talk_time_change():
    """A talk moved to a different time is detected as moved."""
    with scopes_disabled():
        submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
        event = submission.event
        room = RoomFactory(event=event)
        start_time = event.datetime_from
        end_time = start_time + dt.timedelta(hours=1)
        new_start = start_time + dt.timedelta(hours=3)
        new_end = end_time + dt.timedelta(hours=3)

        schedule_v1 = event.wip_schedule
        TalkSlotFactory(
            schedule=schedule_v1,
            submission=submission,
            room=room,
            start=start_time,
            end=end_time,
        )
        schedule_v1.version = "v1"
        schedule_v1.published = now() - dt.timedelta(hours=2)
        schedule_v1.save()

        schedule_v2 = ScheduleFactory(event=event)
        TalkSlotFactory(
            schedule=schedule_v2,
            submission=submission,
            room=room,
            start=new_start,
            end=new_end,
        )
        schedule_v2.version = "v2"
        schedule_v2.published = now()
        schedule_v2.save()

    with scopes_disabled():
        result = calculate_schedule_changes(schedule_v2)

    assert result["action"] == "update"
    assert result["count"] == 1
    assert len(result["moved_talks"]) == 1
    assert result["moved_talks"][0]["old_start"] == start_time.astimezone(event.tz)
    assert result["moved_talks"][0]["new_start"] == new_start.astimezone(event.tz)


@pytest.mark.django_db
def test_calculate_schedule_changes_mixed():
    """Multiple changes (new, canceled, moved) are all detected."""
    with scopes_disabled():
        sub_kept = SubmissionFactory(state=SubmissionStates.CONFIRMED)
        event = sub_kept.event
        sub_new = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub_canceled = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        room1 = RoomFactory(event=event)
        room2 = RoomFactory(event=event)
        start_time = event.datetime_from
        end_time = start_time + dt.timedelta(hours=1)

        schedule_v1 = event.wip_schedule
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
        schedule_v1.version = "v1"
        schedule_v1.published = now() - dt.timedelta(hours=2)
        schedule_v1.save()

        schedule_v2 = ScheduleFactory(event=event)
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
        schedule_v2.version = "v2"
        schedule_v2.published = now()
        schedule_v2.save()

    with scopes_disabled():
        result = calculate_schedule_changes(schedule_v2)

    assert result["action"] == "update"
    assert result["count"] == 3
    assert len(result["new_talks"]) == 1
    assert result["new_talks"][0].submission == sub_new
    assert len(result["canceled_talks"]) == 1
    assert result["canceled_talks"][0].submission == sub_canceled
    assert len(result["moved_talks"]) == 1
    assert result["moved_talks"][0]["submission"] == sub_kept


@pytest.mark.django_db
def test_calculate_schedule_changes_submission_loses_slot():
    """When a submission has two slots and loses one, the lost slot is canceled."""
    with scopes_disabled():
        submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
        event = submission.event
        room = RoomFactory(event=event)
        start = event.datetime_from
        end = start + dt.timedelta(hours=1)

        schedule_v1 = event.wip_schedule
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
        schedule_v1.version = "v1"
        schedule_v1.published = now() - dt.timedelta(hours=2)
        schedule_v1.save()

        schedule_v2 = ScheduleFactory(event=event)
        TalkSlotFactory(
            schedule=schedule_v2, submission=submission, room=room, start=start, end=end
        )
        schedule_v2.version = "v2"
        schedule_v2.published = now()
        schedule_v2.save()

    with scopes_disabled():
        result = calculate_schedule_changes(schedule_v2)

    assert result["count"] == 1
    assert len(result["canceled_talks"]) == 1
    assert result["canceled_talks"][0].submission == submission


@pytest.mark.django_db
def test_calculate_schedule_changes_submission_gains_slot():
    """When a submission keeps an existing slot and gains an additional one,
    the new slot is detected via the moved_or_new path."""
    with scopes_disabled():
        submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
        event = submission.event
        room = RoomFactory(event=event)
        start = event.datetime_from
        end = start + dt.timedelta(hours=1)

        schedule_v1 = event.wip_schedule
        TalkSlotFactory(
            schedule=schedule_v1, submission=submission, room=room, start=start, end=end
        )
        schedule_v1.version = "v1"
        schedule_v1.published = now() - dt.timedelta(hours=2)
        schedule_v1.save()

        schedule_v2 = ScheduleFactory(event=event)
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
        schedule_v2.version = "v2"
        schedule_v2.published = now()
        schedule_v2.save()

    with scopes_disabled():
        result = calculate_schedule_changes(schedule_v2)

    assert result["count"] == 1
    assert len(result["new_talks"]) == 1
    assert result["new_talks"][0].submission == submission


@pytest.mark.django_db
def test_calculate_schedule_changes_multi_slot_submission_both_moved():
    """When a submission has two slots and both change, the submission is only
    handled once (the second entry hits the 'already handled' guard)."""
    with scopes_disabled():
        submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
        event = submission.event
        room1 = RoomFactory(event=event)
        room2 = RoomFactory(event=event)
        start = event.datetime_from
        end = start + dt.timedelta(hours=1)

        schedule_v1 = event.wip_schedule
        TalkSlotFactory(
            schedule=schedule_v1,
            submission=submission,
            room=room1,
            start=start,
            end=end,
        )
        TalkSlotFactory(
            schedule=schedule_v1,
            submission=submission,
            room=room2,
            start=start + dt.timedelta(hours=3),
            end=end + dt.timedelta(hours=3),
        )
        schedule_v1.version = "v1"
        schedule_v1.published = now() - dt.timedelta(hours=2)
        schedule_v1.save()

        schedule_v2 = ScheduleFactory(event=event)
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
        schedule_v2.version = "v2"
        schedule_v2.published = now()
        schedule_v2.save()

    with scopes_disabled():
        result = calculate_schedule_changes(schedule_v2)

    assert result["count"] == 2
    assert len(result["moved_talks"]) == 2


@pytest.mark.usefixtures("locmem_cache")
@pytest.mark.django_db
def test_invalidate_cached_schedule_changes(event):
    with scope(event=event):
        schedule = event.wip_schedule
        cache_key = f"schedule_{schedule.id}_changes"
        event.cache.set(cache_key, "cached_data")
        assert event.cache.get(cache_key) == "cached_data"

        invalidate_cached_schedule_changes(schedule)

        assert event.cache.get(cache_key) is None


@pytest.mark.usefixtures("locmem_cache")
@pytest.mark.django_db
def test_get_cached_schedule_changes_caches_result(event):
    """First call calculates changes; second call returns cached result."""
    with scope(event=event):
        schedule = event.wip_schedule
        cache_key = f"schedule_{schedule.id}_changes"

        assert event.cache.get(cache_key) is None

        result = get_cached_schedule_changes(schedule)

        assert result["action"] == "create"
        cached_data = json.loads(event.cache.get(cache_key))
        assert cached_data["action"] == "create"


@pytest.mark.usefixtures("locmem_cache")
@pytest.mark.django_db
def test_get_cached_schedule_changes_uses_cache():
    """When valid cache exists, it is used instead of recalculating."""
    with scopes_disabled():
        submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
        event = submission.event
        room = RoomFactory(event=event)
        start_time = event.datetime_from
        end_time = start_time + dt.timedelta(hours=1)

        schedule_v1 = event.wip_schedule
        TalkSlotFactory(
            schedule=schedule_v1,
            submission=submission,
            room=room,
            start=start_time,
            end=end_time,
        )
        schedule_v1.version = "v1"
        schedule_v1.published = now() - dt.timedelta(hours=2)
        schedule_v1.save()

        schedule_v2 = ScheduleFactory(event=event)
        schedule_v2.version = "v2"
        schedule_v2.published = now()
        schedule_v2.save()

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
@pytest.mark.django_db
def test_get_cached_schedule_changes_invalid_json_recalculates(event):
    """Corrupted cache data triggers recalculation instead of crashing."""
    with scope(event=event):
        schedule = event.wip_schedule
        cache_key = f"schedule_{schedule.id}_changes"
        event.cache.set(cache_key, "not valid json {{{")

        result = get_cached_schedule_changes(schedule)

        assert result["action"] == "create"


@pytest.mark.usefixtures("locmem_cache")
@pytest.mark.django_db
def test_get_cached_schedule_changes_versioned_schedule():
    """get_cached_schedule_changes works correctly for released schedules."""
    with scopes_disabled():
        sub = SubmissionFactory(state=SubmissionStates.CONFIRMED)
        event = sub.event
        room = RoomFactory(event=event)
        start = event.datetime_from
        end = start + dt.timedelta(hours=1)

        schedule_v1 = event.wip_schedule
        TalkSlotFactory(
            schedule=schedule_v1, submission=sub, room=room, start=start, end=end
        )
        schedule_v1.version = "v1"
        schedule_v1.published = now() - dt.timedelta(hours=2)
        schedule_v1.save()

        schedule_v2 = ScheduleFactory(event=event)
        TalkSlotFactory(
            schedule=schedule_v2, submission=sub, room=room, start=start, end=end
        )
        schedule_v2.version = "v2"
        schedule_v2.published = now()
        schedule_v2.save()

        result = get_cached_schedule_changes(schedule_v2)

    assert result["action"] == "update"
    assert result["count"] == 0


@pytest.mark.django_db
def test_get_boolean_changes_create_action_with_talks():
    """For a first schedule with talks, _get_boolean_changes returns True."""
    with scopes_disabled():
        submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
        event = submission.event
        TalkSlotFactory(submission=submission)

    changes = {"action": "create", "count": 0}

    with scopes_disabled():
        result = _get_boolean_changes(event.wip_schedule, changes)

    assert result is True


@pytest.mark.django_db
def test_get_boolean_changes_create_action_without_talks(event):
    """For a first schedule without talks, _get_boolean_changes returns False."""
    changes = {"action": "create", "count": 0}

    with scopes_disabled():
        result = _get_boolean_changes(event.wip_schedule, changes)

    assert result is False


@pytest.mark.parametrize(("count", "expected"), ((3, True), (0, False)))
def test_get_boolean_changes_update_action(count, expected):
    changes = {"action": "update", "count": count}

    result = _get_boolean_changes(None, changes)

    assert result is expected


@pytest.mark.usefixtures("locmem_cache")
@pytest.mark.django_db
def test_has_unreleased_schedule_changes_returns_cached(event):
    with scope(event=event):
        event.cache.set("has_unreleased_schedule_changes", True)

        assert has_unreleased_schedule_changes(event) is True


@pytest.mark.usefixtures("locmem_cache")
@pytest.mark.django_db
def test_has_unreleased_schedule_changes_calculates_when_not_cached(event):
    """When no cache exists, calculates and caches the value."""
    with scope(event=event):
        assert event.cache.get("has_unreleased_schedule_changes") is None

        result = has_unreleased_schedule_changes(event)

        assert result is False
        assert event.cache.get("has_unreleased_schedule_changes") is False


@pytest.mark.usefixtures("locmem_cache")
@pytest.mark.django_db
def test_update_unreleased_schedule_changes_with_value(event):
    with scope(event=event):
        update_unreleased_schedule_changes(event, True)

        assert event.cache.get("has_unreleased_schedule_changes") is True


@pytest.mark.usefixtures("locmem_cache")
@pytest.mark.django_db
def test_update_unreleased_schedule_changes_recalculates_when_none(event):
    """Passing value=None triggers recalculation."""
    with scope(event=event):
        event.cache.set("has_unreleased_schedule_changes", True)

        update_unreleased_schedule_changes(event, None)

        assert event.cache.get("has_unreleased_schedule_changes") is False


@pytest.mark.django_db
def test_freeze_schedule_basic():
    """Freezing creates a released schedule with comment and a new WIP schedule."""
    with scopes_disabled():
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
    with scopes_disabled():
        assert released.talks.count() == 1
        assert new_wip.talks.count() == 1


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_freeze_schedule_rejects_already_frozen():
    """Cannot freeze a schedule that already has a version."""
    with scopes_disabled():
        event = EventFactory()
        wip = event.wip_schedule
        released, _ = freeze_schedule(wip, "v1", notify_speakers=False)

    with scopes_disabled(), pytest.raises(ValueError, match="already versioned"):
        freeze_schedule(released, "v2")


@pytest.mark.django_db
def test_freeze_schedule_sets_visibility_for_confirmed_and_breaks():
    """After freeze, confirmed talks and breaks are visible; other talks are not."""
    with scopes_disabled():
        confirmed = SubmissionFactory(state=SubmissionStates.CONFIRMED)
        event = confirmed.event
        unconfirmed = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
        room = RoomFactory(event=event)
        wip = event.wip_schedule
        start = event.datetime_from
        end = start + dt.timedelta(hours=1)

        TalkSlotFactory(
            schedule=wip, submission=confirmed, room=room, start=start, end=end
        )
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

    with scopes_disabled():
        confirmed_slot = released.talks.get(submission=confirmed)
        unconfirmed_slot = released.talks.get(submission=unconfirmed)
        break_slot = released.talks.get(slot_type=SlotType.BREAK)

    assert confirmed_slot.is_visible is True
    assert unconfirmed_slot.is_visible is False
    assert break_slot.is_visible is True


@pytest.mark.django_db
def test_freeze_schedule_removes_blockers_from_released():
    """Blockers are deleted from the released schedule but kept in the new WIP."""
    with scopes_disabled():
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

    with scopes_disabled():
        assert released.talks.filter(slot_type=SlotType.BLOCKER).count() == 0
        assert new_wip.talks.filter(slot_type=SlotType.BLOCKER).count() == 1


@pytest.mark.django_db
def test_freeze_schedule_fires_signal(event, register_signal_handler):
    """The schedule_release signal fires with the correct schedule and event."""
    received = []

    def handler(signal, sender, **kwargs):
        received.append(kwargs)

    register_signal_handler(schedule_release, handler)

    with scope(event=event):
        released, _ = freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    assert len(received) == 1
    assert received[0]["schedule"] == released


@pytest.mark.django_db
def test_freeze_schedule_invalidates_wip_cache():
    """After freeze, event.wip_schedule returns the new WIP schedule."""
    with scopes_disabled():
        event = EventFactory()
        old_wip = event.wip_schedule
        freeze_schedule(old_wip, "v1", notify_speakers=False)

    with scopes_disabled():
        assert event.wip_schedule.version is None
        assert event.wip_schedule.pk != old_wip.pk


@pytest.mark.usefixtures("locmem_cache")
@pytest.mark.django_db
def test_freeze_schedule_clears_unreleased_changes_flag():
    with scopes_disabled():
        event = EventFactory()
        event.cache.set("has_unreleased_schedule_changes", True)
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    assert event.cache.get("has_unreleased_schedule_changes") is False


@pytest.mark.django_db
def test_freeze_schedule_with_notify_speakers():
    """Freezing with notify_speakers=True generates speaker notifications."""
    with scopes_disabled():
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

    with scopes_disabled():
        assert QueuedMail.objects.filter(to_users=speaker.user).count() == 1


@pytest.mark.django_db
def test_unfreeze_schedule_basic():
    """Unfreezing resets the WIP schedule to match an older released version."""
    with scopes_disabled():
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
        released_v1, _ = freeze_schedule(
            event.wip_schedule, "v1", notify_speakers=False
        )

        # Modify WIP: remove the slot
        wip = event.wip_schedule
        wip.talks.all().update(room=None, start=None, end=None)
        _, _ = freeze_schedule(wip, "v2", notify_speakers=False)

        # Unfreeze to v1
        _, new_wip = unfreeze_schedule(released_v1)

    with scopes_disabled():
        assert new_wip.version is None
        assert new_wip.talks.filter(submission=submission).count() == 1


@pytest.mark.django_db
def test_unfreeze_schedule_rejects_wip(event):
    """Cannot unfreeze a schedule that has no version."""
    with scope(event=event), pytest.raises(ValueError, match="not released yet"):
        unfreeze_schedule(event.wip_schedule)


@pytest.mark.django_db
def test_unfreeze_schedule_preserves_talks_from_both_versions():
    """Unfreezing merges talks from the old version and the current WIP
    (the bug72 scenario: talks added after v1 are preserved)."""
    with scopes_disabled():
        sub1 = SubmissionFactory(state=SubmissionStates.CONFIRMED)
        event = sub1.event
        room = RoomFactory(event=event)
        start = event.datetime_from
        end = start + dt.timedelta(hours=1)

        TalkSlotFactory(
            schedule=event.wip_schedule,
            submission=sub1,
            room=room,
            start=start,
            end=end,
        )
        released_v1, _ = freeze_schedule(
            event.wip_schedule, "v1", notify_speakers=False
        )

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

    with scopes_disabled():
        assert new_wip.talks.count() == 2
        submission_ids = set(new_wip.talks.values_list("submission_id", flat=True))
        assert submission_ids == {sub1.pk, sub2.pk}


@pytest.mark.usefixtures("locmem_cache")
@pytest.mark.django_db
def test_unfreeze_schedule_clears_unreleased_changes_flag():
    with scopes_disabled():
        event = EventFactory()
        released, _ = freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        event.cache.set("has_unreleased_schedule_changes", True)

        unfreeze_schedule(released)

    assert event.cache.get("has_unreleased_schedule_changes") is False


@pytest.mark.django_db
def test_deserialize_schedule_changes_canceled_missing_slot_skips():
    """Canceled talk entries with a nonexistent slot ID are silently skipped."""
    with scopes_disabled():
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


@pytest.mark.django_db
def test_deserialize_schedule_changes_null_submission_codes():
    """Entries with null submission_code skip submission lookup but still process."""
    with scopes_disabled():
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


@pytest.mark.django_db
def test_deserialize_schedule_changes_slot_exists_no_matching_submission():
    """When a slot exists but its submission_code has no match, the slot is
    still appended (without overwriting its submission)."""
    with scopes_disabled():
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


@pytest.mark.django_db
def test_deserialize_schedule_changes_moved_with_null_rooms():
    """Moved talks with null old_room/new_room are deserialized correctly."""
    with scopes_disabled():
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
