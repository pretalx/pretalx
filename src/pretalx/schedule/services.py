# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import json
from collections import defaultdict, namedtuple
from contextlib import suppress

from django.conf import settings
from django.db import models, transaction
from django.db.utils import DatabaseError
from django.utils.dateparse import parse_datetime
from django.utils.timezone import now

from pretalx.agenda.tasks import export_schedule_html
from pretalx.schedule.signals import schedule_release


def serialize_schedule_changes(changes: dict) -> dict:
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


def deserialize_schedule_changes(serialized: dict, event) -> dict:
    # Collect all IDs we need to fetch
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

    from pretalx.schedule.models import Room, TalkSlot
    from pretalx.submission.models import Submission

    submissions_by_code = {}
    if submission_codes:
        submissions_by_code = {
            sub.code: sub
            for sub in Submission.objects.filter(code__in=submission_codes, event=event)
            .select_related("event")
            .prefetch_related("speakers")
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
            changes["new_talks"].append(slot)

    for item in serialized["canceled_talks"]:
        slot = slots_by_id.get(item["id"])
        if slot:
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

    Slot = namedtuple("Slot", ["submission", "room", "local_start"])
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
        if entry.submission in handled_submissions or not entry.submission:
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
    old_slots_filtered = [
        slot
        for slot in all_old_slots
        if not any(slot.is_same_slot(other_slot) for other_slot in all_new_slots)
    ]
    new_slots_filtered = [
        slot
        for slot in all_new_slots
        if not any(slot.is_same_slot(other_slot) for other_slot in all_old_slots)
    ]
    diff = len(old_slots_filtered) - len(new_slots_filtered)

    if diff > 0:
        canceled = old_slots_filtered[:diff]
        old_slots_filtered = old_slots_filtered[diff:]
    elif diff < 0:
        diff = -diff
        new = new_slots_filtered[:diff]
        new_slots_filtered = new_slots_filtered[diff:]

    for move in zip(old_slots_filtered, new_slots_filtered):
        old_slot = move[0]
        new_slot = move[1]
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
            return deserialize_schedule_changes(serialized, schedule.event)

    result = calculate_schedule_changes(schedule)

    # Cache the result depending on schedule status:
    # WIP schedules: 60 seconds cache
    # Released schedules: 10 minutes cache
    timeout = 60 if schedule.version is None else 600

    with suppress(Exception):
        serialized = serialize_schedule_changes(result)
        schedule.event.cache.set(cache_key, json.dumps(serialized), timeout)

    # Update the unreleased changes flag when WIP schedule changes are recalculated
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
    cache_key = "has_unreleased_schedule_changes"
    cached_value = event.cache.get(cache_key)

    if cached_value is not None:
        return cached_value

    value = _get_boolean_changes(event.wip_schedule)
    update_unreleased_schedule_changes(event, value)
    return value


def update_unreleased_schedule_changes(event, value=None):
    cache_key = "has_unreleased_schedule_changes"
    if value is None:
        invalidate_cached_schedule_changes(event.wip_schedule)
        value = _get_boolean_changes(event.wip_schedule)
    # Cache for 24 hours
    event.cache.set(cache_key, value, 24 * 60 * 60)


def freeze_schedule(
    schedule, name: str, user=None, notify_speakers: bool = True, comment: str = None
):
    """Freeze a schedule as a new version."""

    if name in ("wip", "latest"):
        raise Exception(f'Cannot use reserved name "{name}" for schedule version.')
    if schedule.version:
        raise Exception(
            f'Cannot freeze schedule version: already versioned as "{schedule.version}".'
        )
    if not name:
        raise Exception("Cannot create schedule version without a version name.")

    from pretalx.schedule.models import TalkSlot
    from pretalx.submission.models import SubmissionStates

    with transaction.atomic():
        schedule.version = name
        schedule.comment = comment
        schedule.published = now()

        # Create WIP schedule first, to avoid race conditions
        from pretalx.schedule.models import Schedule

        wip_schedule = Schedule.objects.create(event=schedule.event)

        schedule.save(update_fields=["published", "version", "comment"])
        schedule.log_action("pretalx.schedule.release", person=user, orga=True)

        # Set visibility
        schedule.talks.all().update(is_visible=False)
        schedule.talks.filter(
            models.Q(submission__state=SubmissionStates.CONFIRMED)
            | models.Q(submission__isnull=True),
            start__isnull=False,
        ).update(is_visible=True)

        talks = []
        for talk in schedule.talks.select_related("submission", "room").all():
            talks.append(talk.copy_to_schedule(wip_schedule, save=False))
        TalkSlot.objects.bulk_create(talks)

    if notify_speakers:
        # Complete refresh to avoid dealing with stale data
        schedule = schedule.__class__.objects.get(pk=schedule.pk)
        schedule.generate_notifications(save=True)

    with suppress(AttributeError):
        del wip_schedule.event.wip_schedule
    with suppress(AttributeError):
        del wip_schedule.event.current_schedule

    schedule_release.send_robust(schedule.event, schedule=schedule, user=user)

    if schedule.event.get_feature_flag("export_html_on_release"):
        if not settings.CELERY_TASK_ALWAYS_EAGER:
            export_schedule_html.apply_async(
                kwargs={"event_id": schedule.event.id}, ignore_result=True
            )
        else:
            schedule.event.cache.set("rebuild_schedule_export", True, None)

    # Clear the unreleased changes flag since we just released a schedule
    update_unreleased_schedule_changes(schedule.event, False)

    return schedule, wip_schedule


def unfreeze_schedule(schedule, user=None):
    """Resets the current WIP schedule to an older schedule version."""
    from pretalx.schedule.models import Schedule, TalkSlot

    if not schedule.version:
        raise Exception("Cannot unfreeze schedule version: not released yet.")

    submission_ids = schedule.talks.all().values_list("submission_id", flat=True)
    talks = schedule.event.wip_schedule.talks.exclude(submission_id__in=submission_ids)
    try:
        # We force evaluation to catch the DatabaseError early
        talks = list(talks.union(schedule.talks.all()))
    except DatabaseError:  # SQLite cannot deal with ordered querysets in union()
        talks = set(talks) | set(schedule.talks.all())

    with transaction.atomic():
        wip_schedule = Schedule.objects.create(event=schedule.event)
        new_talks = []
        for talk in talks:
            new_talks.append(talk.copy_to_schedule(wip_schedule, save=False))
        TalkSlot.objects.bulk_create(new_talks)

        schedule.event.wip_schedule.talks.all().delete()
        schedule.event.wip_schedule.delete()

    # Clear the unreleased changes flag since we just released a schedule
    update_unreleased_schedule_changes(schedule.event, False)

    with suppress(AttributeError):
        del wip_schedule.event.wip_schedule

    return schedule, wip_schedule
