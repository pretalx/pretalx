import json
from datetime import datetime, timedelta

import dateutil.parser
import pytest
from django_scopes import scope, scopes_disabled

from pretalx.api.versions import LEGACY
from tests.factories import RoomFactory, TalkSlotFactory

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_room_list_requires_auth_for_non_public_event(client, event):
    """Unauthenticated room list on a non-public event returns 401."""
    with scopes_disabled():
        RoomFactory(event=event)

    response = client.get(event.api_urls.rooms, follow=True)

    assert response.status_code == 401


@pytest.mark.django_db
def test_room_list_accessible_on_public_event_with_schedule(
    client, public_event_with_schedule, published_talk_slot
):
    """Unauthenticated room list works on a public event with a released schedule."""
    event = public_event_with_schedule
    with scopes_disabled():
        room = published_talk_slot.room

    response = client.get(event.api_urls.rooms, follow=True)

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["results"][0]["id"] == room.pk


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_room_list_query_count(
    client, event, orga_token, item_count, django_assert_num_queries
):
    """Query count for room list is constant regardless of item count."""
    with scopes_disabled():
        for _ in range(item_count):
            RoomFactory(event=event)

    with django_assert_num_queries(12):
        response = client.get(
            event.api_urls.rooms,
            follow=True,
            headers={"Authorization": f"Token {orga_token.token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == item_count


@pytest.mark.django_db
def test_room_detail_accessible_with_token(client, event, orga_token):
    """Authenticated orga can view a single room's details."""
    with scopes_disabled():
        room = RoomFactory(event=event, name="Main Hall", capacity=200)

    response = client.get(
        event.api_urls.rooms + f"{room.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == room.pk
    assert data["name"]["en"] == "Main Hall"
    assert data["capacity"] == 200
    assert isinstance(data["name"], dict)


@pytest.mark.django_db
def test_room_detail_locale_override(client, event, orga_token):
    """The ?lang= parameter makes i18n name fields return a plain string."""
    with scopes_disabled():
        room = RoomFactory(event=event, name="Workshop Room")

    response = client.get(
        event.api_urls.rooms + f"{room.pk}/?lang=en",
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["name"], str)
    assert data["name"] == "Workshop Room"


@pytest.mark.django_db
def test_room_log_returns_action_history(client, event, orga_token, orga_user):
    """The /log/ sub-endpoint returns logged actions for a room."""
    with scopes_disabled():
        room = RoomFactory(event=event)
    with scope(event=event):
        room.log_action("pretalx.test.action", data={"key": "val"}, person=orga_user)

    response = client.get(
        event.api_urls.rooms + f"{room.pk}/log/",
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    log_entry = data["results"][0]
    assert log_entry["action_type"] == "pretalx.test.action"
    assert log_entry["data"] == {"key": "val"}
    assert log_entry["person"]["code"] == orga_user.code


@pytest.mark.django_db
def test_room_create_with_write_token(client, event, orga_write_token):
    """POST with a write token creates a new room and logs the action."""
    response = client.post(
        event.api_urls.rooms,
        follow=True,
        data={"name": "New Room", "capacity": 100},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201
    with scopes_disabled():
        room = event.rooms.get(name="New Room")
        assert room.capacity == 100
        assert room.logged_actions().filter(action_type="pretalx.room.create").exists()


@pytest.mark.django_db
def test_room_create_rejected_with_read_token(client, event, orga_token):
    """POST with a read-only token returns 403 and creates nothing."""
    response = client.post(
        event.api_urls.rooms,
        follow=True,
        data={"name": "Forbidden Room"},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        assert not event.rooms.filter(name="Forbidden Room").exists()


@pytest.mark.django_db
def test_room_update_with_write_token(client, event, orga_write_token):
    """PATCH with a write token updates the room and logs changes."""
    with scopes_disabled():
        room = RoomFactory(event=event, name="Old Name")

    response = client.patch(
        event.api_urls.rooms + f"{room.pk}/",
        follow=True,
        data=json.dumps({"name": "New Name"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200
    with scopes_disabled():
        room.refresh_from_db()
        assert room.name == "New Name"
        action = room.logged_actions().get(action_type="pretalx.room.update")
        assert action.data["changes"]["name"] == {"old": "Old Name", "new": "New Name"}


@pytest.mark.django_db
def test_room_update_rejected_with_read_token(client, event, orga_token):
    """PATCH with a read-only token returns 403 and changes nothing."""
    with scopes_disabled():
        room = RoomFactory(event=event, name="Original")

    response = client.patch(
        event.api_urls.rooms + f"{room.pk}/",
        follow=True,
        data=json.dumps({"name": "Changed"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        room.refresh_from_db()
        assert room.name == "Original"


@pytest.mark.django_db
def test_room_delete_with_write_token(client, event, orga_write_token):
    """DELETE with a write token removes the room and logs the action."""
    with scopes_disabled():
        room = RoomFactory(event=event)
        room_pk = room.pk

    response = client.delete(
        event.api_urls.rooms + f"{room_pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 204
    with scopes_disabled():
        assert not event.rooms.filter(pk=room_pk).exists()
        assert event.logged_actions().filter(action_type="pretalx.room.delete").exists()


@pytest.mark.django_db
def test_room_delete_rejected_with_read_token(client, event, orga_token):
    """DELETE with a read-only token returns 403 and keeps the room."""
    with scopes_disabled():
        room = RoomFactory(event=event)

    response = client.delete(
        event.api_urls.rooms + f"{room.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        assert event.rooms.filter(pk=room.pk).exists()


@pytest.mark.django_db
def test_room_delete_protected_when_in_schedule(client, event, orga_write_token):
    """Deleting a room that has talk slots returns 400 with an error message."""
    with scopes_disabled():
        room = RoomFactory(event=event)
        TalkSlotFactory(room=room, submission__event=event)

    response = client.delete(
        event.api_urls.rooms + f"{room.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    with scopes_disabled():
        assert event.rooms.filter(pk=room.pk).exists()


@pytest.mark.django_db
def test_room_create_with_availabilities(client, event, orga_write_token):
    """POST with availabilities creates the room and its availabilities."""
    start = datetime.combine(event.date_from, datetime.min.time()).replace(
        tzinfo=event.tz
    )
    end = start + timedelta(hours=2)

    response = client.post(
        event.api_urls.rooms,
        follow=True,
        data=json.dumps(
            {
                "name": "Avail Room",
                "availabilities": [
                    {"start": start.isoformat(), "end": end.isoformat()}
                ],
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert len(data["availabilities"]) == 1
    assert dateutil.parser.isoparse(data["availabilities"][0]["start"]) == start
    assert dateutil.parser.isoparse(data["availabilities"][0]["end"]) == end
    with scopes_disabled():
        room = event.rooms.get(name="Avail Room")
        assert room.availabilities.count() == 1


@pytest.mark.django_db
def test_room_update_availabilities(client, event, orga_write_token):
    """PATCH replaces existing availabilities with the new set."""
    with scopes_disabled():
        room = RoomFactory(event=event)
    start1 = datetime.combine(event.date_from, datetime.min.time()).replace(
        tzinfo=event.tz
    )
    end1 = start1 + timedelta(hours=2)
    start2 = start1 + timedelta(hours=3)
    end2 = start2 + timedelta(hours=2)

    client.patch(
        event.api_urls.rooms + f"{room.pk}/",
        follow=True,
        data=json.dumps(
            {"availabilities": [{"start": start1.isoformat(), "end": end1.isoformat()}]}
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    response = client.patch(
        event.api_urls.rooms + f"{room.pk}/",
        follow=True,
        data=json.dumps(
            {"availabilities": [{"start": start2.isoformat(), "end": end2.isoformat()}]}
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["availabilities"]) == 1
    assert dateutil.parser.isoparse(data["availabilities"][0]["start"]) == start2
    assert dateutil.parser.isoparse(data["availabilities"][0]["end"]) == end2
    with scopes_disabled():
        room.refresh_from_db()
        assert room.availabilities.count() == 1


@pytest.mark.django_db
def test_room_remove_availabilities(client, event, orga_write_token):
    """PATCH with an empty availabilities list removes all availabilities."""
    with scopes_disabled():
        room = RoomFactory(event=event)
    start = datetime.combine(event.date_from, datetime.min.time()).replace(
        tzinfo=event.tz
    )
    end = start + timedelta(hours=2)

    client.patch(
        event.api_urls.rooms + f"{room.pk}/",
        follow=True,
        data=json.dumps(
            {"availabilities": [{"start": start.isoformat(), "end": end.isoformat()}]}
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    response = client.patch(
        event.api_urls.rooms + f"{room.pk}/",
        follow=True,
        data=json.dumps({"availabilities": []}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200
    assert response.json()["availabilities"] == []
    with scopes_disabled():
        assert room.availabilities.count() == 0


@pytest.mark.django_db
def test_room_create_merges_overlapping_availabilities(client, event, orga_write_token):
    """Overlapping availabilities are merged into a single availability."""
    start1 = datetime.combine(event.date_from, datetime.min.time()).replace(
        tzinfo=event.tz
    )
    end1 = start1 + timedelta(hours=3)
    start2 = start1 + timedelta(hours=1)
    end2 = start1 + timedelta(hours=4)

    response = client.post(
        event.api_urls.rooms,
        follow=True,
        data=json.dumps(
            {
                "name": "Overlap Room",
                "availabilities": [
                    {"start": start1.isoformat(), "end": end1.isoformat()},
                    {"start": start2.isoformat(), "end": end2.isoformat()},
                ],
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert len(data["availabilities"]) == 1
    assert dateutil.parser.isoparse(data["availabilities"][0]["start"]) == start1
    assert dateutil.parser.isoparse(data["availabilities"][0]["end"]) == end2


@pytest.mark.django_db
def test_room_create_with_availabilities_uses_event_timezone(
    client, event, orga_write_token
):
    """Room availability times are returned in the event's timezone, not UTC."""
    event.timezone = "Europe/Berlin"
    event.save()
    start = datetime.combine(event.date_from, datetime.min.time())
    end = start + timedelta(hours=2)

    response = client.post(
        event.api_urls.rooms,
        follow=True,
        data=json.dumps(
            {
                "name": "Timezone Room",
                "availabilities": [
                    {"start": start.isoformat(), "end": end.isoformat()}
                ],
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert "Z" not in data["availabilities"][0]["start"]
    assert "+00:00" not in data["availabilities"][0]["end"]


@pytest.mark.django_db
def test_room_legacy_api_version(client, event, orga_token):
    """Requesting with the legacy Pretalx-Version header returns legacy format."""
    with scopes_disabled():
        room = RoomFactory(event=event)

    response = client.get(
        event.api_urls.rooms + f"{room.pk}/",
        follow=True,
        headers={
            "Authorization": f"Token {orga_token.token}",
            "Pretalx-Version": LEGACY,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == room.pk
    assert "url" in data
    assert "uuid" not in data
    orga_token.refresh_from_db()
    assert orga_token.version == "LEGACY"


@pytest.mark.django_db
def test_room_invalid_api_version_returns_400(client, event, orga_token):
    """An invalid Pretalx-Version header returns 400."""
    with scopes_disabled():
        room = RoomFactory(event=event)

    response = client.get(
        event.api_urls.rooms + f"{room.pk}/",
        follow=True,
        headers={
            "Authorization": f"Token {orga_token.token}",
            "Pretalx-Version": "INVALID",
        },
    )

    assert response.status_code == 400
    assert "id" not in response.json()
    orga_token.refresh_from_db()
    assert not orga_token.version
