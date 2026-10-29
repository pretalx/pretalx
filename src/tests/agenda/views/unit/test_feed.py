# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import urllib.parse

import pytest
from django.http import Http404
from django.test import RequestFactory
from django_scopes import scope

from pretalx.agenda.views.feed import ScheduleFeed
from pretalx.schedule.domain.release import freeze_schedule
from tests.factories import EventFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_schedule_feed_get_object_returns_event(event):
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1")

    rf = RequestFactory()
    request = rf.get("/")
    request.event = event
    request.user = UserFactory()

    feed = ScheduleFeed()

    with scope(event=event):
        result = feed.get_object(request)

    assert result == event


def test_schedule_feed_get_object_raises_404_without_permission(event):
    rf = RequestFactory()
    request = rf.get("/")
    request.event = event
    request.user = UserFactory()

    feed = ScheduleFeed()

    with scope(event=event), pytest.raises(Http404):
        feed.get_object(request)


def test_schedule_feed_items_returns_published_schedules_newest_first(event):
    assert list(ScheduleFeed().items(event)) == []

    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1")
        freeze_schedule(event.wip_schedule, "v2")

    result = list(ScheduleFeed().items(event))

    assert [schedule.version for schedule in result] == ["v2", "v1"]


def test_schedule_feed_item_fields_escape_name_and_version():
    event = EventFactory(name="My\x0bEvent")
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1 beta#final")
        schedule = event.schedules.get(version="v1 beta#final")
        feed = ScheduleFeed()

        assert (
            feed.item_title(schedule) == "New MyEvent schedule released (v1 beta#final)"
        )
        assert (
            feed.item_link(schedule)
            == f"{event.urls.changelog.full()}#{urllib.parse.quote('v1 beta#final', safe='')}"
        )
        assert feed.item_pubdate(schedule) == schedule.published
        description = feed.item_description(schedule)

    assert "\x0b" not in description
    assert "MyEvent" in description
