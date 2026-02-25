# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import urllib.parse
from collections import defaultdict

from django.contrib.syndication.views import Feed
from django.http import Http404
from django.template.loader import render_to_string
from django.utils import feedgenerator

from pretalx.common.text.xml import strip_control_characters
from pretalx.schedule.models import TalkSlot
from pretalx.schedule.services import calculate_schedule_changes


class ScheduleFeed(Feed):
    feed_type = feedgenerator.Atom1Feed

    def get_object(self, request, *args, **kwargs):
        if not request.user.has_perm("schedule.list_schedule", request.event):
            raise Http404
        return request.event

    def title(self, obj):
        return f"{strip_control_characters(obj.name)} schedule updates"

    def link(self, obj):
        return obj.urls.schedule.full()

    def feed_url(self, obj):
        return obj.urls.feed.full()

    def feed_guid(self, obj):
        return obj.urls.feed.full()

    def description(self, obj):
        return f"Updates to the {strip_control_characters(obj.name)} schedule."

    def items(self, obj):
        schedules = list(
            obj.schedules.filter(version__isnull=False)
            .select_related("event")
            .order_by("-published")
        )
        if not schedules:
            return schedules

        # Pre-set previous_schedule to avoid per-item queries.
        # Since schedules are ordered by -published, the next item is the previous version.
        for i, schedule in enumerate(schedules):
            schedule.__dict__["previous_schedule"] = (
                schedules[i + 1] if i + 1 < len(schedules) else None
            )

        # Batch-load all scheduled talk slots in a single query
        all_schedule_ids = [s.pk for s in schedules]
        all_slots = (
            TalkSlot.objects.filter(
                schedule_id__in=all_schedule_ids,
                room__isnull=False,
                start__isnull=False,
                is_visible=True,
                submission__isnull=False,
            )
            .select_related("submission", "submission__event", "room")
            .with_sorted_speakers()
        )
        slots_by_schedule = defaultdict(list)
        for slot in all_slots:
            slots_by_schedule[slot.schedule_id].append(slot)
        for schedule in schedules:
            schedule.__dict__["scheduled_talks"] = slots_by_schedule.get(
                schedule.pk, []
            )

        # Pre-compute changes to avoid per-item queries during rendering
        for schedule in schedules:
            schedule.__dict__["changes"] = calculate_schedule_changes(schedule)

        return schedules

    def item_title(self, item):
        return f"New {strip_control_characters(item.event.name)} schedule released ({strip_control_characters(item.version)})"

    def item_description(self, item):
        content = render_to_string("agenda/feed/description.html", {"obj": item})
        return strip_control_characters(content)

    def item_link(self, item):
        url = item.event.urls.changelog.full()
        return f"{url}#{urllib.parse.quote(item.version, safe='')}"

    def item_pubdate(self, item):
        return item.published
