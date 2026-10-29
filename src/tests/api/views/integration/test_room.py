# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from datetime import datetime, timedelta

import dateutil.parser
import pytest
from django_scopes import scope, scopes_disabled

from pretalx.api.versions import UNSUPPORTED_VERSION_MESSAGE
from tests.factories import RoomFactory, TalkSlotFactory

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_room_list_requires_auth_for_non_public_event(client, event):
    with scopes_disabled():
        RoomFactory(event=event)

    response = client.get(event.api_urls.rooms, follow=True)

    assert response.status_code == 401


def test_room_list_on_public_event_with_schedule(
    client, public_event_with_schedule, published_talk_slot
):
    event = public_event_with_schedule
    with scopes_disabled():
        room = published_talk_slot.room
        RoomFactory(event=event, hidden=True)
    with scope(event=event):
        room.log_action("pretalx.test.action", data={"key": "val"}, person=None)

    response = client.get(event.api_urls.rooms, follow=True)
    log = client.get(event.api_urls.rooms + f"{room.pk}/log/", follow=True)

    assert response.status_code == 200
    assert [r["id"] for r in response.json()["results"]] == [room.pk]
    assert log.status_code == 403


@pytest.mark.parametrize("item_count", (1, 3))
def test_room_list_query_count(
    client, event, orga_read_token, item_count, django_assert_num_queries
):
    with scopes_disabled():
        RoomFactory.create_batch(item_count, event=event)

    with django_assert_num_queries(12):
        response = client.get(
            event.api_urls.rooms,
            follow=True,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == item_count


def test_room_detail_with_read_token(client, event, orga_read_token):
    with scopes_disabled():
        room = RoomFactory(event=event, name="Main Hall", capacity=200)
    url = event.api_urls.rooms + f"{room.pk}/"
    headers = {"Authorization": f"Token {orga_read_token.token}"}

    invalid_version = client.get(
        url, follow=True, headers={**headers, "Pretalx-Version": "INVALID"}
    )

    assert invalid_version.status_code == 400
    assert "id" not in invalid_version.json()
    orga_read_token.refresh_from_db()
    assert not orga_read_token.version

    response = client.get(url, follow=True, headers=headers)
    localised = client.get(url + "?lang=en", follow=True, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == room.pk
    assert data["name"] == {"en": "Main Hall"}
    assert data["capacity"] == 200
    assert localised.status_code == 200
    assert localised.json()["name"] == "Main Hall"
    orga_read_token.refresh_from_db()
    assert orga_read_token.version == "v2"


def test_room_create_with_write_token(client, event, orga_write_token):
    start1 = datetime.combine(event.date_from, datetime.min.time()).replace(
        tzinfo=event.tz
    )
    end1 = start1 + timedelta(hours=3)
    start2 = start1 + timedelta(hours=1)
    end2 = start1 + timedelta(hours=4)

    response = client.post(
        event.api_urls.rooms,
        follow=True,
        data={
            "name": "New Room",
            "capacity": 100,
            "availabilities": [
                {"start": start1.isoformat(), "end": end1.isoformat()},
                {"start": start2.isoformat(), "end": end2.isoformat()},
            ],
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert len(data["availabilities"]) == 1
    assert dateutil.parser.isoparse(data["availabilities"][0]["start"]) == start1
    assert dateutil.parser.isoparse(data["availabilities"][0]["end"]) == end2
    with scopes_disabled():
        room = event.rooms.get(name="New Room")
        assert room.capacity == 100
        assert room.availabilities.count() == 1
        assert room.logged_actions().filter(action_type="pretalx.room.create").exists()


def test_room_write_rejected_with_read_token(client, event, orga_read_token):
    response = client.post(
        event.api_urls.rooms,
        follow=True,
        data={"name": "Forbidden Room"},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        assert not event.rooms.filter(name="Forbidden Room").exists()


def test_room_update_log_and_delete_with_write_token(
    client, event, orga_write_token, orga_user
):
    with scopes_disabled():
        room = RoomFactory(event=event, name="Old Name")
    url = event.api_urls.rooms + f"{room.pk}/"
    headers = {"Authorization": f"Token {orga_write_token.token}"}

    response = client.patch(
        url,
        follow=True,
        data={"name": "New Name", "hidden": True},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["hidden"] is True
    with scopes_disabled():
        room.refresh_from_db()
        assert room.name == "New Name"
        assert room.hidden is True

    log = client.get(url + "log/", follow=True, headers=headers)

    assert log.status_code == 200
    data = log.json()
    assert data["count"] == 1
    log_entry = data["results"][0]
    assert log_entry["action_type"] == "pretalx.room.update"
    assert log_entry["data"]["changes"]["name"] == {
        "old": "Old Name",
        "new": "New Name",
    }
    assert log_entry["person"]["code"] == orga_user.code

    response = client.delete(url, follow=True, headers=headers)

    assert response.status_code == 204
    with scopes_disabled():
        assert not event.rooms.filter(pk=room.pk).exists()
        assert event.logged_actions().filter(action_type="pretalx.room.delete").exists()


def test_room_hide_and_delete_refused_for_scheduled_room(
    client, event, orga_write_token
):
    with scopes_disabled():
        room = RoomFactory(event=event)
        TalkSlotFactory(room=room, submission__event=event)
    url = event.api_urls.rooms + f"{room.pk}/"
    headers = {"Authorization": f"Token {orga_write_token.token}"}

    hidden = client.patch(
        url,
        follow=True,
        data={"hidden": True},
        content_type="application/json",
        headers=headers,
    )
    deleted = client.delete(url, follow=True, headers=headers)

    assert hidden.status_code == 400
    assert "neither be deleted nor hidden" in hidden.json()["hidden"][0]
    assert deleted.status_code == 400
    with scopes_disabled():
        room.refresh_from_db()
        assert room.hidden is False


def test_room_list_filters_by_hidden_for_orga(client, event, orga_read_token):
    with scopes_disabled():
        visible = RoomFactory(event=event)
        hidden = RoomFactory(event=event, hidden=True)
    headers = {"Authorization": f"Token {orga_read_token.token}"}

    unfiltered = client.get(event.api_urls.rooms, follow=True, headers=headers)
    visible_only = client.get(
        event.api_urls.rooms + "?hidden=false", follow=True, headers=headers
    )
    hidden_only = client.get(
        event.api_urls.rooms + "?hidden=true", follow=True, headers=headers
    )

    assert {room["id"] for room in unfiltered.json()["results"]} == {
        visible.pk,
        hidden.pk,
    }
    assert [room["id"] for room in visible_only.json()["results"]] == [visible.pk]
    assert [room["id"] for room in hidden_only.json()["results"]] == [hidden.pk]


def test_room_update_availabilities(client, event, orga_write_token):
    with scopes_disabled():
        room = RoomFactory(event=event)
    url = event.api_urls.rooms + f"{room.pk}/"
    headers = {"Authorization": f"Token {orga_write_token.token}"}
    start1 = datetime.combine(event.date_from, datetime.min.time()).replace(
        tzinfo=event.tz
    )
    end1 = start1 + timedelta(hours=2)
    start2 = start1 + timedelta(hours=3)
    end2 = start2 + timedelta(hours=2)

    client.patch(
        url,
        follow=True,
        data={
            "availabilities": [{"start": start1.isoformat(), "end": end1.isoformat()}]
        },
        content_type="application/json",
        headers=headers,
    )
    response = client.patch(
        url,
        follow=True,
        data={
            "availabilities": [{"start": start2.isoformat(), "end": end2.isoformat()}]
        },
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["availabilities"]) == 1
    assert dateutil.parser.isoparse(data["availabilities"][0]["start"]) == start2
    assert dateutil.parser.isoparse(data["availabilities"][0]["end"]) == end2
    with scopes_disabled():
        assert room.availabilities.count() == 1

    response = client.patch(
        url,
        follow=True,
        data={"availabilities": []},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["availabilities"] == []
    with scopes_disabled():
        assert room.availabilities.count() == 0


def test_room_create_with_availabilities_uses_event_timezone(
    client, event, orga_write_token
):
    event.timezone = "Europe/Berlin"
    event.save()
    start = datetime.combine(event.date_from, datetime.min.time())
    end = start + timedelta(hours=2)

    response = client.post(
        event.api_urls.rooms,
        follow=True,
        data={
            "name": "Timezone Room",
            "availabilities": [{"start": start.isoformat(), "end": end.isoformat()}],
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert "Z" not in data["availabilities"][0]["start"]
    assert "+00:00" not in data["availabilities"][0]["end"]


def test_room_list_with_removed_legacy_token_version_returns_400(
    client, event, orga_read_token
):
    orga_read_token.version = "LEGACY"
    orga_read_token.save()

    response = client.get(
        event.api_urls.rooms,
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == UNSUPPORTED_VERSION_MESSAGE.format(
        version="LEGACY"
    )


def test_room_list_uses_page_number_pagination(client, event, orga_read_token):
    with scopes_disabled():
        rooms = RoomFactory.create_batch(2, event=event)

    response = client.get(
        event.api_urls.rooms + "?page_size=1&page=2",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert [room["id"] for room in data["results"]] == [rooms[1].pk]
    assert data["next"] is None
    assert data["previous"] is not None
