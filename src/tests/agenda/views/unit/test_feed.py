# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import urllib.parse

import pytest
from django.http import Http404
from django.test import RequestFactory
from django_scopes import scope

from pretalx.agenda.views.feed import ScheduleFeed
from pretalx.common.text.xml import strip_control_characters
from tests.factories import EventFactory, UserFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_schedule_feed_get_object_returns_event(event):
    with scope(event=event):
        event.release_schedule("v1")

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


def test_schedule_feed_items_returns_published_schedules(event):
    with scope(event=event):
        event.release_schedule("v1")
        event.release_schedule("v2")

    result = list(ScheduleFeed().items(event))

    assert len(result) == 2
    assert result[0].version == "v2"
    assert result[1].version == "v1"


def test_schedule_feed_items_excludes_wip_schedule(event):
    result = list(ScheduleFeed().items(event))

    assert result == []


def test_schedule_feed_item_title(event):
    with scope(event=event):
        event.release_schedule("v1")
    schedule = event.schedules.filter(version="v1").first()

    result = ScheduleFeed().item_title(schedule)

    expected = f"New {strip_control_characters(event.name)} schedule released ({strip_control_characters(schedule.version)})"
    assert result == expected


def test_schedule_feed_item_link(event):
    with scope(event=event):
        event.release_schedule("v1")
    schedule = event.schedules.filter(version="v1").first()

    result = ScheduleFeed().item_link(schedule)

    expected = f"{event.urls.changelog.full()}#{urllib.parse.quote('v1', safe='')}"
    assert result == expected


def test_schedule_feed_item_link_encodes_version(event):
    with scope(event=event):
        event.release_schedule("v1 beta/final")
    schedule = event.schedules.filter(version="v1 beta/final").first()

    result = ScheduleFeed().item_link(schedule)

    assert urllib.parse.quote("v1 beta/final", safe="") in result


def test_schedule_feed_item_pubdate(event):
    with scope(event=event):
        event.release_schedule("v1")
    schedule = event.schedules.filter(version="v1").first()

    result = ScheduleFeed().item_pubdate(schedule)

    assert result == schedule.published


def test_schedule_feed_item_description_strips_control_characters():
    event = EventFactory(name="My\x0bEvent")
    with scope(event=event):
        event.release_schedule("v1")
        schedule = event.schedules.filter(version="v1").first()

        result = ScheduleFeed().item_description(schedule)

    assert "\x0b" not in result
    assert "MyEvent" in result
