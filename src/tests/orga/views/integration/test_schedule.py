import datetime as dt
import json
from uuid import uuid4

import pytest
from django.core.files.base import ContentFile
from django_scopes import scopes_disabled

from pretalx.common.models.file import CachedFile
from pretalx.event.models import Event
from pretalx.schedule.models import Room, Schedule, TalkSlot
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    AnswerFactory,
    AvailabilityFactory,
    CachedFileFactory,
    QuestionFactory,
    RoomFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TrackFactory,
)
from tests.utils import make_orga_user

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_schedule_view_accessible_for_orga(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(event.orga_urls.schedule)

    assert response.status_code == 200


@pytest.mark.django_db
def test_schedule_view_anonymous_redirects(client, event):
    response = client.get(event.orga_urls.schedule)

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_schedule_view_user_without_permission_gets_404(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=False)
    client.force_login(user)

    response = client.get(event.orga_urls.schedule)

    assert response.status_code == 404


@pytest.mark.django_db
def test_schedule_release_view_accessible(client, talk_slot):
    event = talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(event.orga_urls.release_schedule)

    assert response.status_code == 200


@pytest.mark.django_db
def test_schedule_release_creates_new_schedule(client, talk_slot):
    event = talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        schedule_count = Schedule.objects.filter(event=event).count()
    client.force_login(user)

    response = client.post(
        event.orga_urls.release_schedule, data={"version": "v1.0"}, follow=True
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert Schedule.objects.filter(event=event).count() == schedule_count + 1
        assert Schedule.objects.filter(event=event, version="v1.0").exists()


@pytest.mark.django_db
def test_schedule_release_rejects_duplicate_version(client, talk_slot):
    event = talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    client.post(event.orga_urls.release_schedule, data={"version": "v1.0"})

    with scopes_disabled():
        initial_count = Schedule.objects.filter(event=event).count()

    response = client.post(
        event.orga_urls.release_schedule, data={"version": "v1.0"}, follow=True
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert Schedule.objects.filter(event=event).count() == initial_count


@pytest.mark.django_db
def test_schedule_release_anonymous_redirects(client, event):
    response = client.post(event.orga_urls.release_schedule, data={"version": "v1.0"})

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_schedule_toggle_flips_visibility(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    event.feature_flags["show_schedule"] = True
    event.save()
    client.force_login(user)

    response = client.get(event.orga_urls.toggle_schedule, follow=True)

    assert response.status_code == 200
    updated = Event.objects.get(pk=event.pk)
    assert updated.feature_flags["show_schedule"] is False

    response = client.get(event.orga_urls.toggle_schedule, follow=True)

    assert response.status_code == 200
    updated = Event.objects.get(pk=event.pk)
    assert updated.feature_flags["show_schedule"] is True


@pytest.mark.django_db
def test_schedule_toggle_anonymous_redirects(client, event):
    response = client.get(event.orga_urls.toggle_schedule)

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_schedule_resend_mails_with_released_schedule(client, published_talk_slot):
    event = published_talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        initial_mail_count = event.queued_mails.count()
    client.force_login(user)

    response = client.post(event.orga_urls.schedule + "resend_mails", follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert event.queued_mails.count() > initial_mail_count
        mail = event.queued_mails.last()
        assert published_talk_slot.submission.title in mail.text
        assert str(published_talk_slot.room.name) in mail.text
        assert mail.submissions.count() == 1


@pytest.mark.django_db
def test_schedule_resend_mails_without_released_schedule(client, event):
    """Warning message when no schedule has been released yet."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        initial_mail_count = event.queued_mails.count()
    client.force_login(user)

    response = client.post(event.orga_urls.schedule + "resend_mails", follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert event.queued_mails.count() == initial_mail_count


@pytest.mark.django_db
def test_schedule_resend_mails_anonymous_redirects(client, event):
    response = client.post(event.orga_urls.schedule + "resend_mails")

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_talk_list_returns_talks_json(client, talk_slot):
    event = talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(event.orga_urls.talks_api)

    assert response.status_code == 200
    data = response.json()
    assert "talks" in data
    assert len(data["talks"]) >= 1
    assert data["talks"][0]["title"]


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_talk_list_query_count(client, event, item_count, django_assert_num_queries):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        for _ in range(item_count):
            speaker = SpeakerFactory(event=event)
            sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
            sub.speakers.add(speaker)
            TalkSlotFactory(submission=sub, is_visible=True)
    client.force_login(user)

    with django_assert_num_queries(12):
        response = client.get(event.orga_urls.talks_api)

    assert response.status_code == 200
    data = response.json()
    assert len(data["talks"]) == item_count


@pytest.mark.django_db
def test_talk_list_with_version_parameter(client, published_talk_slot):
    event = published_talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(event.orga_urls.talks_api + "?version=v1")

    assert response.status_code == 200
    data = response.json()
    assert "talks" in data


@pytest.mark.django_db
def test_talk_list_with_warnings_parameter(client, talk_slot):
    event = talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(event.orga_urls.talks_api + "?warnings=true")

    assert response.status_code == 200
    data = response.json()
    assert "warnings" in data


@pytest.mark.django_db
def test_talk_list_anonymous_redirects(client, event):
    response = client.get(event.orga_urls.talks_api)

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_talk_list_create_break(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        room = RoomFactory(event=event)
        initial_count = event.wip_schedule.talks.count()
    client.force_login(user)

    response = client.post(
        event.orga_urls.talks_api,
        data=json.dumps({"room": room.pk, "duration": 45, "title": "Coffee Break"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["duration"] == 45
    with scopes_disabled():
        assert event.wip_schedule.talks.count() == initial_count + 1
        slot = event.wip_schedule.talks.filter(submission__isnull=True).first()
        assert str(slot.description) == "Coffee Break"
        assert slot.room == room


@pytest.mark.django_db
def test_talk_list_create_blocker(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        room = RoomFactory(event=event)
    client.force_login(user)

    response = client.post(
        event.orga_urls.talks_api,
        data=json.dumps(
            {
                "room": room.pk,
                "duration": 30,
                "title": "Blocked",
                "slot_type": "blocker",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["slot_type"] == "blocker"


@pytest.mark.django_db
def test_talk_list_create_rejects_invalid_slot_type(client, event):
    """Invalid slot_type falls back to 'break'."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        room = RoomFactory(event=event)
    client.force_login(user)

    response = client.post(
        event.orga_urls.talks_api,
        data=json.dumps({"room": room.pk, "slot_type": "invalid_type"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["slot_type"] == "break"


@pytest.mark.django_db
def test_talk_update_patch_moves_slot(client, talk_slot):
    event = talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        room = talk_slot.room
        new_start = event.datetime_from + dt.timedelta(hours=2)
    client.force_login(user)

    response = client.patch(
        f"{event.orga_urls.schedule_api}talks/{talk_slot.pk}/",
        data=json.dumps({"start": new_start.isoformat(), "room": room.pk}),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == str(talk_slot.submission.title)
    with scopes_disabled():
        talk_slot.refresh_from_db()
        assert talk_slot.start == new_start
        assert talk_slot.room == room


@pytest.mark.django_db
def test_talk_update_patch_with_null_room_keeps_existing_room(client, talk_slot):
    """When room is null in the PATCH payload, the slot keeps its current room."""
    event = talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        original_room = talk_slot.room
        new_start = event.datetime_from + dt.timedelta(hours=2)
    client.force_login(user)

    response = client.patch(
        f"{event.orga_urls.schedule_api}talks/{talk_slot.pk}/",
        data=json.dumps({"start": new_start.isoformat(), "room": None}),
        content_type="application/json",
    )

    assert response.status_code == 200
    with scopes_disabled():
        talk_slot.refresh_from_db()
        assert talk_slot.start == new_start
        assert talk_slot.room == original_room


@pytest.mark.django_db
def test_talk_update_patch_resets_slot(client, talk_slot):
    """PATCH with empty body resets start/end/room to null."""
    event = talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.patch(
        f"{event.orga_urls.schedule_api}talks/{talk_slot.pk}/",
        data=json.dumps({}),
        content_type="application/json",
    )

    assert response.status_code == 200
    with scopes_disabled():
        talk_slot.refresh_from_db()
        assert talk_slot.start is None
        assert talk_slot.end is None
        assert talk_slot.room is None


@pytest.mark.django_db
def test_talk_update_patch_break_with_duration(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        room = RoomFactory(event=event)
        slot = TalkSlotFactory(
            submission=None, schedule=event.wip_schedule, room=room, is_visible=True
        )
        new_start = event.datetime_from + dt.timedelta(hours=1)
    client.force_login(user)

    response = client.patch(
        f"{event.orga_urls.schedule_api}talks/{slot.pk}/",
        data=json.dumps(
            {
                "start": new_start.isoformat(),
                "room": room.pk,
                "duration": 90,
                "title": "Long Break",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    with scopes_disabled():
        slot.refresh_from_db()
        assert slot.duration == 90
        assert str(slot.description) == "Long Break"
        assert slot.start == new_start


@pytest.mark.django_db
def test_talk_update_patch_break_with_explicit_end(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        room = RoomFactory(event=event)
        slot = TalkSlotFactory(
            submission=None, schedule=event.wip_schedule, room=room, is_visible=True
        )
        new_start = event.datetime_from + dt.timedelta(hours=1)
        new_end = new_start + dt.timedelta(minutes=60)
    client.force_login(user)

    response = client.patch(
        f"{event.orga_urls.schedule_api}talks/{slot.pk}/",
        data=json.dumps(
            {
                "start": new_start.isoformat(),
                "end": new_end.isoformat(),
                "room": room.pk,
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    with scopes_disabled():
        slot.refresh_from_db()
        assert slot.duration == 60


@pytest.mark.django_db
def test_talk_update_patch_nonexistent_slot_returns_404(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.patch(
        f"{event.orga_urls.schedule_api}talks/999999/",
        data=json.dumps({"start": "2024-01-01T10:00:00Z"}),
        content_type="application/json",
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_talk_update_delete_break_slot(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        room = RoomFactory(event=event)
        slot = TalkSlotFactory(
            submission=None, schedule=event.wip_schedule, room=room, is_visible=True
        )
        slot_pk = slot.pk
    client.force_login(user)

    response = client.delete(f"{event.orga_urls.schedule_api}talks/{slot_pk}/")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    with scopes_disabled():
        assert not TalkSlot.objects.filter(pk=slot_pk).exists()


@pytest.mark.django_db
def test_talk_update_delete_refuses_submission_slot(client, talk_slot):
    """Cannot delete a slot that has a submission attached."""
    event = talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        initial_count = event.wip_schedule.talks.count()
    client.force_login(user)

    response = client.delete(f"{event.orga_urls.schedule_api}talks/{talk_slot.pk}/")

    assert response.status_code == 200
    data = response.json()
    assert "error" in data
    with scopes_disabled():
        assert event.wip_schedule.talks.count() == initial_count


@pytest.mark.django_db
def test_talk_update_delete_nonexistent_slot_returns_404(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.delete(f"{event.orga_urls.schedule_api}talks/999999/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_talk_update_anonymous_redirects_to_login(client, talk_slot):
    event = talk_slot.submission.event

    response = client.patch(
        f"{event.orga_urls.schedule_api}talks/{talk_slot.pk}/",
        data=json.dumps({}),
        content_type="application/json",
    )

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_schedule_warnings_returns_json(client, talk_slot):
    event = talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(event.orga_urls.schedule_api + "warnings/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


@pytest.mark.django_db
def test_schedule_warnings_anonymous_redirects(client, event):
    response = client.get(event.orga_urls.schedule_api + "warnings/")

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_schedule_availabilities_returns_json(client, talk_slot):
    event = talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(event.orga_urls.schedule_api + "availabilities/")

    assert response.status_code == 200
    data = response.json()
    assert "talks" in data
    assert "rooms" in data


@pytest.mark.django_db
def test_schedule_availabilities_includes_room_availabilities(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        room = RoomFactory(event=event)
        AvailabilityFactory(event=event, room=room)
        speaker = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub.speakers.add(speaker)
        TalkSlotFactory(submission=sub, is_visible=True)
    client.force_login(user)

    response = client.get(event.orga_urls.schedule_api + "availabilities/")

    assert response.status_code == 200
    data = response.json()
    assert str(room.pk) in data["rooms"]
    assert len(data["rooms"][str(room.pk)]) == 1


@pytest.mark.django_db
def test_schedule_availabilities_includes_speaker_availabilities(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker = SpeakerFactory(event=event)
        AvailabilityFactory(event=event, person=speaker)
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub.speakers.add(speaker)
        slot = TalkSlotFactory(submission=sub, is_visible=True)
    client.force_login(user)

    response = client.get(event.orga_urls.schedule_api + "availabilities/")

    assert response.status_code == 200
    data = response.json()
    assert str(slot.pk) in data["talks"]
    assert len(data["talks"][str(slot.pk)]) == 1


@pytest.mark.django_db
def test_schedule_availabilities_anonymous_redirects(client, event):
    response = client.get(event.orga_urls.schedule_api + "availabilities/")

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_quick_schedule_view_get_accessible(client, talk_slot):
    event = talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        RoomFactory(event=event)
    client.force_login(user)

    response = client.get(
        f"{event.orga_urls.schedule}quick/{talk_slot.submission.code}/"
    )

    assert response.status_code == 200


@pytest.mark.django_db
def test_quick_schedule_view_post_schedules_talk(client, talk_slot):
    event = talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        room = RoomFactory(event=event)
    client.force_login(user)

    response = client.post(
        f"{event.orga_urls.schedule}quick/{talk_slot.submission.code}/",
        data={
            "start_date": event.date_from.strftime("%Y-%m-%d"),
            "start_time": "10:00:00",
            "room": room.pk,
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        talk_slot.refresh_from_db()
        assert talk_slot.room == room
        assert talk_slot.start.date() == event.date_from


@pytest.mark.django_db
def test_quick_schedule_anonymous_redirects_to_login(client, talk_slot):
    event = talk_slot.submission.event

    response = client.get(
        f"{event.orga_urls.schedule}quick/{talk_slot.submission.code}/"
    )

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_room_list_accessible(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        RoomFactory(event=event, name="Main Hall")
    client.force_login(user)

    response = client.get(event.orga_urls.room_settings)

    assert response.status_code == 200
    assert "Main Hall" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_room_list_query_count(client, event, item_count, django_assert_num_queries):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        rooms = [RoomFactory(event=event, name=f"Room {i}") for i in range(item_count)]
    client.force_login(user)

    with django_assert_num_queries(18):
        response = client.get(event.orga_urls.room_settings)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(str(room.name) in content for room in rooms)


@pytest.mark.django_db
def test_room_list_anonymous_redirects(client, event):
    response = client.get(event.orga_urls.room_settings)

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_room_list_user_without_permission_gets_404(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=False)
    client.force_login(user)

    response = client.get(event.orga_urls.room_settings)

    assert response.status_code == 404


@pytest.mark.django_db
def test_room_create(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        availability = AvailabilityFactory(event=event)
    client.force_login(user)

    response = client.post(
        event.orga_urls.new_room,
        data={
            "name_0": "Workshop Room",
            "guid": str(uuid4()),
            "availabilities": json.dumps(
                {
                    "availabilities": [
                        {
                            "start": availability.start.strftime("%Y-%m-%d %H:%M:00Z"),
                            "end": availability.end.strftime("%Y-%m-%d %H:%M:00Z"),
                        }
                    ]
                }
            ),
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert event.rooms.count() == 1
        room = event.rooms.first()
        assert str(room.name) == "Workshop Room"
        assert room.availabilities.count() == 1


@pytest.mark.django_db
def test_room_create_user_without_permission_gets_404(client, event):
    """Users with can_change_submissions but not can_change_event_settings cannot create rooms."""
    with scopes_disabled():
        user = make_orga_user(
            event, can_change_submissions=True, can_change_event_settings=False
        )
    client.force_login(user)

    response = client.post(
        event.orga_urls.new_room,
        data={"name_0": "Room", "guid": str(uuid4()), "availabilities": "{}"},
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_room_update(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        room = RoomFactory(event=event, name="Old Name")
        AvailabilityFactory(event=event, room=room)
    client.force_login(user)

    new_guid = str(uuid4())
    response = client.post(
        room.urls.edit,
        data={
            "name_0": "New Name",
            "guid": new_guid,
            "availabilities": json.dumps({"availabilities": []}),
        },
        follow=True,
    )

    assert response.status_code == 200
    with scopes_disabled():
        room.refresh_from_db()
        assert str(room.name) == "New Name"
        assert room.availabilities.count() == 0
        action = room.logged_actions().get(action_type="pretalx.room.update")
        assert action.data["changes"]["guid"]["new"]
        assert not action.data["changes"]["guid"]["old"]
        assert action.data["changes"]["name"]["new"] == {"en": "New Name"}


@pytest.mark.django_db
def test_room_delete_unused_room(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        room = RoomFactory(event=event)
    client.force_login(user)

    response = client.get(room.urls.delete)
    assert response.status_code == 200

    response = client.post(room.urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert not Room.objects.filter(pk=room.pk).exists()


@pytest.mark.django_db
def test_room_delete_used_room_fails(client, talk_slot):
    """Rooms in use by a talk slot cannot be deleted (ProtectedError)."""
    event = talk_slot.submission.event
    room = talk_slot.room
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(room.urls.delete, follow=True)

    assert response.status_code == 200
    with scopes_disabled():
        assert Room.objects.filter(pk=room.pk).exists()


@pytest.mark.django_db
def test_schedule_export_view_accessible(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.get(event.orga_urls.schedule_export)

    assert response.status_code == 200


@pytest.mark.django_db
def test_schedule_export_view_anonymous_redirects(client, event):
    response = client.get(event.orga_urls.schedule_export)

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_schedule_export_csv(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        question = QuestionFactory(
            event=event, question="Dietary needs", target="submission"
        )
        AnswerFactory(question=question, submission=submission, answer="Vegan")
    client.force_login(user)

    response = client.post(
        event.orga_urls.schedule_export,
        data={
            "target": "all",
            "title": "on",
            "speaker_ids": "on",
            f"question_{question.id}": "on",
            "export_format": "csv",
            "data_delimiter": "comma",
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert content == (
        f"ID,Proposal title,Speaker IDs,Dietary needs\r\n"
        f"{submission.code},{submission.title},{speaker.code},Vegan\r\n"
    )


@pytest.mark.django_db
def test_schedule_export_json(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)
        submission.speakers.add(speaker)
        question = QuestionFactory(
            event=event, question="Dietary needs", target="submission"
        )
        AnswerFactory(question=question, submission=submission, answer="Vegan")
    client.force_login(user)

    response = client.post(
        event.orga_urls.schedule_export,
        data={
            "target": "all",
            "title": "on",
            "speaker_ids": "on",
            f"question_{question.id}": "on",
            "export_format": "json",
        },
    )

    assert response.status_code == 200
    data = json.loads(response.content.decode())
    assert data == [
        {
            "ID": submission.code,
            "Proposal title": submission.title,
            "Speaker IDs": [speaker.code],
            "Dietary needs": "Vegan",
        }
    ]


@pytest.mark.django_db
def test_schedule_export_csv_without_delimiter_returns_form(client, event):
    """CSV export without data_delimiter is invalid and re-renders the form."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(
        event.orga_urls.schedule_export,
        data={"target": "rejected", "title": "on", "export_format": "csv"},
    )

    assert response.status_code == 200
    assert response.content.decode().strip().startswith("<!doctype")


@pytest.mark.django_db
def test_schedule_export_empty_data_redirects(client, event):
    """When export matches no submissions, the user is redirected back."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(
        event.orga_urls.schedule_export,
        data={"target": "rejected", "title": "on", "export_format": "json"},
    )

    assert response.status_code == 302
    assert response.url == event.orga_urls.schedule_export


@pytest.mark.django_db
def test_schedule_export_track_limited_reviewer_gets_404(client, event):
    """Track-limited reviewers cannot access the schedule export view."""
    with scopes_disabled():
        track = TrackFactory(event=event)
        submission = SubmissionFactory(event=event, track=track)
        speaker = SpeakerFactory(event=event)
        submission.speakers.add(speaker)
        user = make_orga_user(
            event,
            is_reviewer=True,
            can_change_organiser_settings=False,
            can_change_event_settings=False,
            can_change_submissions=False,
            all_events=False,
        )
        user.teams.first().limit_tracks.add(track)
    client.force_login(user)

    response = client.get(event.orga_urls.schedule_export)
    assert response.status_code == 404

    response = client.post(
        event.orga_urls.schedule_export,
        data={"target": "submitted", "title": "on", "export_format": "json"},
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_schedule_export_trigger_without_cached_file(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(event.orga_urls.schedule_export_trigger)

    assert response.status_code == 302
    assert response.url == event.orga_urls.schedule_export_download


@pytest.mark.django_db
def test_schedule_export_trigger_deletes_cached_file(client, event, locmem_cache):
    """When a cached export file exists, triggering clears it before redirect."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        cached_file = CachedFileFactory()
        event.cache.set("schedule_export_cached_file", str(cached_file.id), None)
    client.force_login(user)

    response = client.post(event.orga_urls.schedule_export_trigger)

    assert response.status_code == 302
    with scopes_disabled():
        assert not CachedFile.objects.filter(id=cached_file.id).exists()
        assert event.cache.get("schedule_export_cached_file") is None


@pytest.mark.django_db
def test_schedule_export_trigger_anonymous_redirects(client, event):
    response = client.post(event.orga_urls.schedule_export_trigger)

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_schedule_export_download_starts_task(client, published_talk_slot):
    """Requesting the download endpoint starts an async export task."""
    event = published_talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.get(event.orga_urls.schedule_export_download, follow=True)

    assert response.status_code == 200


@pytest.mark.django_db
def test_schedule_export_download_serves_cached_file(client, event, locmem_cache):
    """When a valid cached file exists, download serves it directly."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        cached_file = CachedFileFactory()
        cached_file.file.save("test.zip", ContentFile(b"fake zip content"))
        event.cache.set("schedule_export_cached_file", str(cached_file.id), None)
    client.force_login(user)

    response = client.get(event.orga_urls.schedule_export_download)

    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"


@pytest.mark.django_db
def test_schedule_export_download_clears_stale_cache(
    client, published_talk_slot, locmem_cache
):
    """When cache points to a CachedFile without actual file data, the stale
    entry is cleared and the async download flow starts fresh."""
    event = published_talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        cached_file = CachedFileFactory()
    client.force_login(user)

    fresh_event = Event.objects.get(pk=event.pk)
    fresh_event.cache.set("schedule_export_cached_file", str(cached_file.id), None)
    assert fresh_event.cache.get("schedule_export_cached_file") == str(cached_file.id)

    response = client.get(event.orga_urls.schedule_export_download, follow=True)

    assert response.status_code == 200


@pytest.mark.django_db
def test_schedule_export_download_with_cached_file_param_skips_cache_lookup(
    client, published_talk_slot
):
    """When cached_file is in GET params, the event-level cache lookup is
    skipped and the async download handler processes the param directly."""
    event = published_talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.get(
        event.orga_urls.schedule_export_download,
        data={"cached_file": "nonexistent"},
        follow=True,
    )

    assert response.status_code == 200


@pytest.mark.django_db
def test_schedule_export_download_anonymous_redirects(client, event):
    response = client.get(event.orga_urls.schedule_export_download)

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_schedule_availabilities_multi_speaker_intersection(client, event):
    """When a talk has multiple speakers, their availabilities are intersected."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker1 = SpeakerFactory(event=event)
        speaker2 = SpeakerFactory(event=event)
        AvailabilityFactory(event=event, person=speaker1)
        AvailabilityFactory(event=event, person=speaker2)
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub.speakers.add(speaker1)
        sub.speakers.add(speaker2)
        slot = TalkSlotFactory(submission=sub, is_visible=True)
    client.force_login(user)

    response = client.get(event.orga_urls.schedule_api + "availabilities/")

    assert response.status_code == 200
    data = response.json()
    assert str(slot.pk) in data["talks"]
    assert isinstance(data["talks"][str(slot.pk)], list)


@pytest.mark.django_db
def test_schedule_availabilities_multi_speaker_no_availabilities(client, event):
    """When a talk has multiple speakers with no availabilities, empty list is returned."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        speaker1 = SpeakerFactory(event=event)
        speaker2 = SpeakerFactory(event=event)
        sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        sub.speakers.add(speaker1)
        sub.speakers.add(speaker2)
        slot = TalkSlotFactory(submission=sub, is_visible=True)
    client.force_login(user)

    response = client.get(event.orga_urls.schedule_api + "availabilities/")

    assert response.status_code == 200
    data = response.json()
    assert data["talks"][str(slot.pk)] == []


@pytest.mark.django_db
def test_talk_update_patch_talk_with_submission_uses_submission_duration(
    client, talk_slot
):
    """When patching a talk slot (with submission) with start but no duration/end,
    the submission's duration is used for the end time."""
    event = talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        new_start = event.datetime_from + dt.timedelta(hours=3)
    client.force_login(user)

    response = client.patch(
        f"{event.orga_urls.schedule_api}talks/{talk_slot.pk}/",
        data=json.dumps({"start": new_start.isoformat(), "room": talk_slot.room.pk}),
        content_type="application/json",
    )

    assert response.status_code == 200
    with scopes_disabled():
        talk_slot.refresh_from_db()
        expected_duration = talk_slot.submission.get_duration()
        assert talk_slot.start == new_start
        assert talk_slot.end == new_start + dt.timedelta(minutes=expected_duration)


@pytest.mark.django_db
def test_talk_update_patch_break_preserves_duration_when_not_provided(client, event):
    """When patching a break slot with start but no duration/end, the existing
    duration is preserved."""
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        room = RoomFactory(event=event)
        start = event.datetime_from
        end = start + dt.timedelta(minutes=45)
        slot = TalkSlotFactory(
            submission=None,
            schedule=event.wip_schedule,
            room=room,
            start=start,
            end=end,
            is_visible=True,
        )
        new_start = event.datetime_from + dt.timedelta(hours=2)
    client.force_login(user)

    response = client.patch(
        f"{event.orga_urls.schedule_api}talks/{slot.pk}/",
        data=json.dumps({"start": new_start.isoformat(), "room": room.pk}),
        content_type="application/json",
    )

    assert response.status_code == 200
    with scopes_disabled():
        slot.refresh_from_db()
        assert slot.start == new_start
        assert slot.duration == 45
