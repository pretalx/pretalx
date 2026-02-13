# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import urllib.parse

from django.contrib.syndication.views import Feed
from django.http import Http404
from django.template.loader import render_to_string
from django.utils import feedgenerator

from pretalx.common.text.xml import strip_control_characters


class ScheduleFeed(Feed):
    feed_type = feedgenerator.Atom1Feed

    def get_object(self, request, *args, **kwargs):
        if not request.user.has_perm("schedule.list_schedule", request.event):
            raise Http404()
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
        return obj.schedules.filter(version__isnull=False).order_by("-published")

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
