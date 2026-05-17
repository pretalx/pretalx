# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import json
from collections import defaultdict
from contextlib import suppress
from typing import NamedTuple

from django.utils.dateparse import parse_datetime
from django_scopes import scope

from pretalx.schedule.models import Room, TalkSlot
from pretalx.submission.models import Submission


def _serialize_changes(changes: dict) -> dict:
    serialized = {
        "count": changes["count"],
        "action": changes["action"],
        "new_talks": [],
        "canceled_talks": [],
        "moved_talks": [],
    }

    for talk in changes["new_talks"]:
        serialized["new_talks"].append(
            {
                "id": talk.id,
                "submission_code": (talk.submission.code if talk.submission else None),
            }
        )

    for talk in changes["canceled_talks"]:
        serialized["canceled_talks"].append(
            {
                "id": talk.id,
                "submission_code": (talk.submission.code if talk.submission else None),
            }
        )

    for moved in changes["moved_talks"]:
        serialized["moved_talks"].append(
            {
                "submission_code": (
                    moved["submission"].code if moved["submission"] else None
                ),
                "old_start": (
                    moved["old_start"].isoformat() if moved["old_start"] else None
                ),
                "new_start": (
                    moved["new_start"].isoformat() if moved["new_start"] else None
                ),
                "old_room": moved["old_room"].pk if moved["old_room"] else None,
                "new_room": moved["new_room"].pk if moved["new_room"] else None,
                "new_info": moved["new_info"],
                "new_slot_id": moved["new_slot"].id if moved["new_slot"] else None,
            }
        )

    return serialized


def _deserialize_changes(serialized: dict, event) -> dict:
    submission_codes = set()
    slot_ids = set()
    room_ids = set()

    for item in serialized["new_talks"] + serialized["canceled_talks"]:
        if item["submission_code"]:
            submission_codes.add(item["submission_code"])
        slot_ids.add(item["id"])

    for item in serialized["moved_talks"]:
        if item["submission_code"]:
            submission_codes.add(item["submission_code"])
        if item["new_slot_id"]:
            slot_ids.add(item["new_slot_id"])
        if item.get("new_room"):
            room_ids.add(item["new_room"])
        if item.get("old_room"):
            room_ids.add(item["old_room"])

    submissions_by_code = {}
    if submission_codes:
        submissions_by_code = {
            sub.code: sub
            for sub in Submission.objects.filter(code__in=submission_codes, event=event)
            .select_related("event")
            .with_sorted_speakers()
        }

    slots_by_id = {}
    if slot_ids:
        slots_by_id = {
            slot.id: slot
            for slot in TalkSlot.objects.filter(id__in=slot_ids).select_related(
                "submission", "room", "schedule"
            )
        }

    rooms_by_id = {}
    if room_ids:
        rooms_by_id = {
            room.id: room for room in Room.objects.filter(id__in=room_ids, event=event)
        }

    changes = {
        "count": serialized["count"],
        "action": serialized["action"],
        "new_talks": [],
        "canceled_talks": [],
        "moved_talks": [],
    }

    for item in serialized["new_talks"]:
        slot = slots_by_id.get(item["id"])
        if slot:
            submission = submissions_by_code.get(item["submission_code"])
            if submission:
                slot.submission = submission
            changes["new_talks"].append(slot)

    for item in serialized["canceled_talks"]:
        slot = slots_by_id.get(item["id"])
        if slot:
            submission = submissions_by_code.get(item["submission_code"])
            if submission:
                slot.submission = submission
            changes["canceled_talks"].append(slot)

    for item in serialized["moved_talks"]:
        submission = (
            submissions_by_code.get(item["submission_code"])
            if item["submission_code"]
            else None
        )
        new_slot = slots_by_id.get(item["new_slot_id"]) if item["new_slot_id"] else None

        if submission:
            old_room = None
            new_room = None
            if item.get("new_room"):
                new_room = rooms_by_id.get(item["new_room"])
            if item.get("old_room"):
                old_room = rooms_by_id.get(item["old_room"])

            changes["moved_talks"].append(
                {
                    "submission": submission,
                    "old_start": (
                        parse_datetime(item["old_start"]) if item["old_start"] else None
                    ),
                    "new_start": (
                        parse_datetime(item["new_start"]) if item["new_start"] else None
                    ),
                    "old_room": old_room,
                    "new_room": new_room,
                    "new_info": item["new_info"],
                    "new_slot": new_slot,
                }
            )

    return changes


def calculate_schedule_changes(schedule) -> dict:
    result = {
        "count": 0,
        "action": "update",
        "new_talks": [],
        "canceled_talks": [],
        "moved_talks": [],
    }

    if not schedule.previous_schedule:
        result["action"] = "create"
        return result

    class Slot(NamedTuple):
        submission: object
        room: object
        local_start: object

    old_slots = {
        Slot(slot.submission, slot.room, slot.local_start): slot
        for slot in schedule.previous_schedule.scheduled_talks
    }
    new_slots = {
        Slot(slot.submission, slot.room, slot.local_start): slot
        for slot in schedule.scheduled_talks
    }

    old_slot_set = set(old_slots.keys())
    new_slot_set = set(new_slots.keys())
    old_submissions = {slot.submission for slot in old_slots}
    new_submissions = {slot.submission for slot in new_slots}
    handled_submissions = set()
    new_by_submission = defaultdict(list)
    old_by_submission = defaultdict(list)

    for slot in new_slot_set:
        new_by_submission[slot.submission].append(new_slots[slot])
    for slot in old_slot_set:
        old_by_submission[slot.submission].append(old_slots[slot])

    moved_or_missing = old_slot_set - new_slot_set - {None}
    moved_or_new = new_slot_set - old_slot_set - {None}

    for entry in moved_or_missing:
        if entry.submission in handled_submissions:
            continue
        if entry.submission not in new_submissions:
            result["canceled_talks"] += old_by_submission[entry.submission]
        else:
            new, canceled, moved = _handle_submission_move(
                entry.submission, old_slots, new_slots
            )
            result["new_talks"] += new
            result["canceled_talks"] += canceled
            result["moved_talks"] += moved
        handled_submissions.add(entry.submission)

    for entry in moved_or_new:
        if entry.submission in handled_submissions:
            continue
        if entry.submission not in old_submissions:
            result["new_talks"] += new_by_submission[entry.submission]
        else:
            new, canceled, moved = _handle_submission_move(
                entry.submission, old_slots, new_slots
            )
            result["new_talks"] += new
            result["canceled_talks"] += canceled
            result["moved_talks"] += moved
        handled_submissions.add(entry.submission)

    result["count"] = (
        len(result["new_talks"])
        + len(result["canceled_talks"])
        + len(result["moved_talks"])
    )

    return result


def _handle_submission_move(submission, old_slots, new_slots):
    new = []
    canceled = []
    moved = []
    all_old_slots = [
        slot for slot in old_slots.values() if slot.submission_id == submission.pk
    ]
    all_new_slots = [
        slot for slot in new_slots.values() if slot.submission_id == submission.pk
    ]
    old_sigs = {(slot.room_id, slot.start) for slot in all_old_slots}
    new_sigs = {(slot.room_id, slot.start) for slot in all_new_slots}
    old_slots_filtered = [
        slot for slot in all_old_slots if (slot.room_id, slot.start) not in new_sigs
    ]
    new_slots_filtered = [
        slot for slot in all_new_slots if (slot.room_id, slot.start) not in old_sigs
    ]
    diff = len(old_slots_filtered) - len(new_slots_filtered)

    if diff > 0:
        canceled = old_slots_filtered[:diff]
        old_slots_filtered = old_slots_filtered[diff:]
    elif diff < 0:
        diff = -diff
        new = new_slots_filtered[:diff]
        new_slots_filtered = new_slots_filtered[diff:]

    for old_slot, new_slot in zip(old_slots_filtered, new_slots_filtered, strict=True):
        moved.append(
            {
                "submission": new_slot.submission,
                "old_start": old_slot.local_start,
                "new_start": new_slot.local_start,
                "old_room": old_slot.room,
                "new_room": new_slot.room,
                "new_info": str(new_slot.room.speaker_info),
                "new_slot": new_slot,
            }
        )
    return new, canceled, moved


def invalidate_cached_schedule_changes(schedule):
    cache_key = f"schedule_{schedule.id}_changes"
    schedule.event.cache.delete(cache_key)


def get_cached_schedule_changes(schedule) -> dict:
    cache_key = f"schedule_{schedule.id}_changes"
    cached_data = schedule.event.cache.get(cache_key)

    if cached_data:
        with suppress(json.JSONDecodeError, KeyError):
            serialized = json.loads(cached_data)
            return _deserialize_changes(serialized, schedule.event)

    result = calculate_schedule_changes(schedule)

    # WIP schedules: 60 seconds cache; released schedules: 10 minutes.
    timeout = 60 if schedule.version is None else 600

    with suppress(Exception):
        serialized = _serialize_changes(result)
        schedule.event.cache.set(cache_key, json.dumps(serialized), timeout)

    if schedule.version is None:
        update_unreleased_schedule_changes(
            schedule.event, _get_boolean_changes(schedule, result)
        )

    return result


def _get_boolean_changes(schedule, changes=None) -> bool:
    changes = changes or schedule.changes
    with suppress(ValueError, AttributeError):
        if changes["action"] == "create":
            return schedule.scheduled_talks.exists()
        return changes["count"] > 0


def has_unreleased_schedule_changes(event) -> bool:
    """Compute whether ``event`` has unreleased WIP schedule changes.

    Prefer ``event.has_unreleased_schedule_changes`` (cached_property on
    Event); it works better in tests and on instances with a broken or
    slow cache, as it additionally caches on the event instance."""
    cache_key = "has_unreleased_schedule_changes"
    cached_value = event.cache.get(cache_key)

    if cached_value is not None:
        return cached_value

    with scope(event=event):
        value = _get_boolean_changes(event.wip_schedule)
    update_unreleased_schedule_changes(event, value)
    return value


def update_unreleased_schedule_changes(event, value=None):
    cache_key = "has_unreleased_schedule_changes"
    if value is None:
        invalidate_cached_schedule_changes(event.wip_schedule)
        value = _get_boolean_changes(event.wip_schedule)
    event.cache.set(cache_key, value, 24 * 60 * 60)
