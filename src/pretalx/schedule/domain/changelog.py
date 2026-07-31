# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from collections import defaultdict

from pretalx.schedule.domain.queries.schedule import published_schedules
from pretalx.schedule.models import Room, TalkSlot
from pretalx.submission.models import Submission


def build_changelog(event, limit=None):
    """Return released schedules of ``event`` hydrated for changelog-style
    presentation (used by the Atom feed).
    """
    schedules = list(published_schedules(event))
    if not schedules:
        return schedules
    if limit:
        schedules = schedules[: limit + 1]

    for i, schedule in enumerate(schedules):
        schedule.__dict__["previous_schedule"] = (
            schedules[i + 1] if i + 1 < len(schedules) else None
        )

    slots = list(
        TalkSlot.objects.filter(
            schedule_id__in=[s.pk for s in schedules],
            room__isnull=False,
            start__isnull=False,
            is_visible=True,
            submission__isnull=False,
        )
    )

    # We populate rooms and submissions manually, as otherwise the query will
    # return each room and each submission roughly once per version, resulting
    # in tens of thousands of wide rows for events with many releases.
    rooms = {
        room.pk: room
        for room in Room.objects.filter(pk__in={slot.room_id for slot in slots})
    }
    submissions = {
        submission.pk: submission
        for submission in Submission.all_objects.filter(
            pk__in={slot.submission_id for slot in slots}
        ).with_sorted_speakers()
    }
    for submission in submissions.values():
        submission.event = event
    schedules_by_id = {schedule.pk: schedule for schedule in schedules}

    slots_by_schedule = defaultdict(list)
    for slot in slots:
        slot.room = rooms[slot.room_id]
        slot.submission = submissions[slot.submission_id]
        slot.schedule = schedules_by_id[slot.schedule_id]
        slots_by_schedule[slot.schedule_id].append(slot)
    for schedule in schedules:
        schedule.__dict__["scheduled_talks"] = slots_by_schedule.get(schedule.pk, [])

    return schedules[:limit] if limit else schedules
