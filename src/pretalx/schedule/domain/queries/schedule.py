# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

from pretalx.schedule.models import TalkSlot

DAY_START_HOUR = 4


def published_schedules(event):
    """Released schedules of ``event``, most recent first, with the event
    preloaded.

    Callers that render the changelog, the Atom feed, or the static HTML
    export all want the same shape: a flat list of all versioned schedules in
    publication order. Use :func:`pretalx.schedule.domain.changelog.build_changelog`
    when ``previous_schedule`` and ``scheduled_talks`` should also be batched
    in.
    """
    return (
        event.schedules.filter(version__isnull=False)
        .select_related("event")
        .order_by("-published")
    )


def get_schedule(event, version, *, queryset=None):
    """Look up a schedule by version, or return None.

    Pass a version or the special strings ``"wip"`` or ``"latest"``.
    """
    queryset = event.schedules.all() if queryset is None else queryset
    queryset = queryset.select_related("event")
    if version == "wip":
        return queryset.filter(version__isnull=True).first()
    if version == "latest":
        if not event.current_schedule:
            return None
        return queryset.filter(pk=event.current_schedule.pk).first()
    return queryset.filter(version=version).first()


def public_talk_slots(event):
    """Talk slots visible to non-orga viewers of ``event``."""
    return TalkSlot.objects.filter(schedule__event=event, is_visible=True).exclude(
        schedule__version__isnull=True
    )


def schedule_day_start(slot):
    local_start = slot.local_start
    day_start = local_start.replace(
        hour=DAY_START_HOUR, minute=0, second=0, microsecond=0
    )
    if local_start.hour < DAY_START_HOUR:
        day_start -= dt.timedelta(days=1)
    return day_start


def _visible_slots(schedule):
    return schedule.talks.filter(
        is_visible=True,
        room__isnull=False,
        start__isnull=False,
        end__isnull=False,
        submission__isnull=False,
    )


def room_neighbour_slots(slot):
    day_start = schedule_day_start(slot)
    same_day_in_room = (
        _visible_slots(slot.schedule)
        .filter(
            room_id=slot.room_id,
            start__gte=day_start,
            start__lt=day_start + dt.timedelta(days=1),
        )
        .exclude(pk=slot.pk)
        .select_related("submission", "submission__event")
    )
    return {
        "previous": same_day_in_room.filter(start__lt=slot.start)
        .order_by("-start")
        .first(),
        "next": same_day_in_room.filter(start__gt=slot.start).order_by("start").first(),
    }


def parallel_slots(slot):
    return (
        _visible_slots(slot.schedule)
        .filter(start__lt=slot.real_end, end__gt=slot.start)
        .exclude(submission_id=slot.submission_id)
        .select_related("submission", "submission__event", "room")
        .order_by("start", "room__position", "room_id")
    )
