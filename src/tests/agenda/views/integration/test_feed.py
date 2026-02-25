import pytest
from django_scopes import scope

from pretalx.common.text.xml import strip_control_characters

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_schedule_feed_renders_atom(client, public_event_with_schedule):
    """The feed renders valid Atom XML with schedule releases."""
    event = public_event_with_schedule

    response = client.get(event.urls.feed)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/atom+xml")
    content = response.content.decode()
    assert strip_control_characters(event.name) in content
    assert "v1" in content


@pytest.mark.django_db
def test_schedule_feed_404_without_permission(client, event, published_talk_slot):
    """The feed returns 404 when the schedule is not publicly visible."""
    response = client.get(event.urls.feed)

    assert response.status_code == 404


@pytest.mark.django_db
def test_schedule_feed_contains_all_released_versions(
    client, public_event_with_schedule
):
    """The feed includes all released schedule versions in order."""
    event = public_event_with_schedule
    with scope(event=event):
        event.release_schedule("v2")

    response = client.get(event.urls.feed)

    assert response.status_code == 200
    content = response.content.decode()
    assert "v1" in content
    assert "v2" in content


@pytest.mark.django_db
def test_schedule_feed_excludes_wip_schedule(client, public_event_with_schedule):
    """The feed does not include the WIP (unpublished) schedule."""
    response = client.get(public_event_with_schedule.urls.feed)

    content = response.content.decode()
    assert "v1" in content
    assert content.count("<entry>") == 1


@pytest.mark.django_db
def test_schedule_feed_item_links_contain_changelog(client, public_event_with_schedule):
    """Each feed entry links to the changelog with a version anchor."""
    response = client.get(public_event_with_schedule.urls.feed)

    content = response.content.decode()
    assert "changelog" in content
    assert "#v1" in content


@pytest.mark.django_db
def test_schedule_feed_strips_control_characters(client, public_event_with_schedule):
    """Control characters in schedule versions are stripped from the feed output."""
    event = public_event_with_schedule
    with scope(event=event):
        event.release_schedule("Version\x0b1")

    response = client.get(event.urls.feed)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Version1" in content
    assert "\x0b" not in content


@pytest.mark.django_db
def test_schedule_feed_accessible_to_organizer(
    client, event, published_talk_slot, organiser_user
):
    """An organizer can access the feed even if the event is not public."""
    client.force_login(organiser_user)

    response = client.get(event.urls.feed)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/atom+xml")


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_schedule_feed_query_count(
    client, public_event_with_schedule, item_count, django_assert_num_queries
):
    """Feed query count is constant regardless of the number of released schedule versions."""
    event = public_event_with_schedule
    with scope(event=event):
        for i in range(1, item_count):  # v1 already released by published_talk_slot
            event.release_schedule(f"v{i + 1}")

    with django_assert_num_queries(9):
        response = client.get(event.urls.feed)

    assert response.status_code == 200
    assert response.content.decode().count("<entry>") == item_count
