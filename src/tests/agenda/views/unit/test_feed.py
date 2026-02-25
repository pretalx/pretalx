import urllib.parse

import pytest
from django.http import Http404
from django.test import RequestFactory
from django_scopes import scope, scopes_disabled

from pretalx.agenda.views.feed import ScheduleFeed
from pretalx.common.text.xml import strip_control_characters
from tests.factories import UserFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_schedule_feed_get_object_returns_event(event):
    """get_object returns the request event when user has list_schedule permission."""
    event.is_public = True
    event.feature_flags["show_schedule"] = True
    event.save()
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


@pytest.mark.django_db
def test_schedule_feed_get_object_raises_404_without_permission(event):
    """get_object raises Http404 when user lacks list_schedule permission."""
    rf = RequestFactory()
    request = rf.get("/")
    request.event = event
    request.user = UserFactory()

    feed = ScheduleFeed()

    with scope(event=event), pytest.raises(Http404):
        feed.get_object(request)


@pytest.mark.django_db
def test_schedule_feed_title(event):
    result = ScheduleFeed().title(event)

    assert result == f"{strip_control_characters(event.name)} schedule updates"


@pytest.mark.django_db
def test_schedule_feed_link(event):
    result = ScheduleFeed().link(event)

    assert result == event.urls.schedule.full()


@pytest.mark.django_db
def test_schedule_feed_feed_url(event):
    result = ScheduleFeed().feed_url(event)

    assert result == event.urls.feed.full()


@pytest.mark.django_db
def test_schedule_feed_feed_guid(event):
    result = ScheduleFeed().feed_guid(event)

    assert result == event.urls.feed.full()


@pytest.mark.django_db
def test_schedule_feed_description(event):
    result = ScheduleFeed().description(event)

    assert result == f"Updates to the {strip_control_characters(event.name)} schedule."


@pytest.mark.django_db
def test_schedule_feed_items_returns_published_schedules(event):
    """items returns only schedules with a version, ordered by -published."""
    with scope(event=event):
        event.release_schedule("v1")
        event.release_schedule("v2")

    with scopes_disabled():
        result = list(ScheduleFeed().items(event))

    assert len(result) == 2
    assert result[0].version == "v2"
    assert result[1].version == "v1"


@pytest.mark.django_db
def test_schedule_feed_items_excludes_wip_schedule(event):
    """items does not include the WIP schedule (version=None)."""
    with scopes_disabled():
        result = list(ScheduleFeed().items(event))

    assert result == []


@pytest.mark.django_db
def test_schedule_feed_item_title(event):
    with scope(event=event):
        event.release_schedule("v1")
    with scopes_disabled():
        schedule = event.schedules.filter(version="v1").first()

    result = ScheduleFeed().item_title(schedule)

    expected = f"New {strip_control_characters(event.name)} schedule released ({strip_control_characters(schedule.version)})"
    assert result == expected


@pytest.mark.django_db
def test_schedule_feed_item_link(event):
    with scope(event=event):
        event.release_schedule("v1")
    with scopes_disabled():
        schedule = event.schedules.filter(version="v1").first()

    result = ScheduleFeed().item_link(schedule)

    expected = f"{event.urls.changelog.full()}#{urllib.parse.quote('v1', safe='')}"
    assert result == expected


@pytest.mark.django_db
def test_schedule_feed_item_link_encodes_version(event):
    """item_link URL-encodes special characters in the version string."""
    with scope(event=event):
        event.release_schedule("v1 beta/final")
    with scopes_disabled():
        schedule = event.schedules.filter(version="v1 beta/final").first()

    result = ScheduleFeed().item_link(schedule)

    assert urllib.parse.quote("v1 beta/final", safe="") in result


@pytest.mark.django_db
def test_schedule_feed_item_pubdate(event):
    with scope(event=event):
        event.release_schedule("v1")
    with scopes_disabled():
        schedule = event.schedules.filter(version="v1").first()

    result = ScheduleFeed().item_pubdate(schedule)

    assert result == schedule.published


@pytest.mark.django_db
def test_schedule_feed_item_description_strips_control_characters(event):
    """item_description renders the template and strips control characters."""
    event.name = "My\x0bEvent"
    event.save()
    with scope(event=event):
        event.release_schedule("v1")
        schedule = event.schedules.filter(version="v1").first()

        result = ScheduleFeed().item_description(schedule)

    assert "\x0b" not in result
    assert "MyEvent" in result
