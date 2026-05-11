# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from collections import defaultdict

from pretalx.schedule.domain.queries.schedule import published_schedules
from pretalx.schedule.models import TalkSlot


def build_changelog(event):
    """Return all released schedules of ``event`` hydrated for changelog-style
    presentation (used by the public changelog page and the Atom feed).
    """
    schedules = list(published_schedules(event))
    if not schedules:
        return schedules

    for i, schedule in enumerate(schedules):
        schedule.__dict__["previous_schedule"] = (
            schedules[i + 1] if i + 1 < len(schedules) else None
        )

    slots = (
        TalkSlot.objects.filter(
            schedule_id__in=[s.pk for s in schedules],
            room__isnull=False,
            start__isnull=False,
            is_visible=True,
            submission__isnull=False,
        )
        .select_related("submission", "submission__event", "room")
        .with_sorted_speakers()
    )
    slots_by_schedule = defaultdict(list)
    for slot in slots:
        slots_by_schedule[slot.schedule_id].append(slot)
    for schedule in schedules:
        schedule.__dict__["scheduled_talks"] = slots_by_schedule.get(schedule.pk, [])

    return schedules
