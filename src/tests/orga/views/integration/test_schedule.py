# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import json
from uuid import uuid4

import pytest
from django.contrib.messages import constants as message_constants
from django.contrib.messages import get_messages
from django.core.files.base import ContentFile
from django_scopes import scopes_disabled

from pretalx.common.models.file import CachedFile
from pretalx.event.models import Event
from pretalx.mail.domain.template import mail_template_by_role
from pretalx.mail.enums import MailTemplateRoles
from pretalx.schedule.domain.release import freeze_schedule
from pretalx.schedule.models import Room, Schedule, TalkSlot
from pretalx.schedule.models.slot import SlotType
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    AnswerFactory,
    AttendeeSignupFactory,
    AvailabilityFactory,
    CachedFileFactory,
    QuestionFactory,
    RoomFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _scheduled_submission(event, room, start_offset=0, **kwargs):
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.CONFIRMED, **kwargs
    )
    start = event.datetime_from + dt.timedelta(hours=start_offset)
    TalkSlotFactory(
        submission=submission,
        schedule=event.wip_schedule,
        room=room,
        start=start,
        end=start + dt.timedelta(hours=1),
        is_visible=True,
    )
    return submission


def test_schedule_view_denied_without_access(client, event):
    response = client.get(event.orga_urls.schedule)
    assert response.status_code == 302
    assert "/login/" in response.url

    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=False)
    client.force_login(user)
    response = client.get(event.orga_urls.schedule)
    assert response.status_code == 404


def test_schedule_release_page_and_release(client, event):
    with scopes_disabled():
        event.feature_flags["attendee_signup"] = True
        event.feature_flags["use_tracks"] = True
        event.save()
        TrackFactory(event=event)
        sub_type = event.cfp.default_type
        sub_type.attendee_signup_required = True
        sub_type.save()
        template = mail_template_by_role(event, MailTemplateRoles.NEW_SCHEDULE)
        template.text = "See {profile_page_url} for {speaker_schedule_new}"
        template.save()
        user = make_orga_user(event, can_change_submissions=True)
        large_room = RoomFactory(event=event, capacity=300)
        unlimited_room = RoomFactory(event=event, capacity=None)
        plain_room = RoomFactory(event=event)
        too_small = _scheduled_submission(
            event,
            large_room,
            submission_type=sub_type,
            attendee_signup_capacity=10,
            track=None,
        )
        unlimited = _scheduled_submission(
            event,
            unlimited_room,
            submission_type=sub_type,
            attendee_signup_capacity=None,
            track=None,
        )
        unnotifiable = _scheduled_submission(event, plain_room, track=None)
        unnotifiable.speakers.add(
            SpeakerFactory(event=event, user=None, email=None, name="No Mail")
        )
        account_only = _scheduled_submission(event, plain_room, 2, track=None)
        account_only.speakers.add(
            SpeakerFactory(
                event=event, user=None, email="managed@example.com", name="Managed"
            )
        )
        schedule_count = Schedule.objects.filter(event=event).count()
    client.force_login(user)

    response = client.get(event.orga_urls.release_schedule)
    assert response.status_code == 200
    body = response.content.decode()
    assert "Sessions with room to spare" in body
    assert f"expand_capacity_{too_small.pk}" in body
    assert "Sessions with unlimited signups" in body
    assert f'href="{unlimited_room.urls.settings_base}"' in body
    assert "cannot be notified" in body
    assert "No Mail" in body
    assert "only work with a pretalx account" in body
    assert "profile_page_url" in body
    assert "Managed" in body
    assert "4 sessions have <strong>not yet been assigned a track</strong>" in body
    for submission in (too_small, unlimited, unnotifiable, account_only):
        assert f'href="{submission.orga_urls.base}"' in body

    response = client.post(
        event.orga_urls.release_schedule,
        data={
            "version": "v1.0",
            "comment": "release",
            "notify_speakers": "on",
            f"expand_capacity_{too_small.pk}": "on",
        },
        follow=True,
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert Schedule.objects.filter(event=event).count() == schedule_count + 1
        assert Schedule.objects.filter(event=event, version="v1.0").exists()
        too_small.refresh_from_db(fields=["attendee_signup_capacity"])
        log_entries = list(
            too_small.logged_actions().filter(action_type="pretalx.submission.update")
        )
    assert too_small.attendee_signup_capacity == 300
    # One bulk-created log entry per expanded capacity, recording the
    # change with old/new values and the user who triggered the freeze.
    assert len(log_entries) == 1
    entry = log_entries[0]
    assert entry.person == user
    assert entry.is_orga_action is True
    assert entry.data["changes"]["attendee_signup_capacity"] == {"old": 10, "new": 300}

    response = client.post(
        event.orga_urls.release_schedule, data={"version": "v1.0"}, follow=True
    )
    assert response.status_code == 200
    with scopes_disabled():
        assert Schedule.objects.filter(event=event).count() == schedule_count + 1


def test_schedule_release_no_warnings_for_reachable_speakers(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        template = mail_template_by_role(event, MailTemplateRoles.NEW_SCHEDULE)
        template.text = "See {profile_page_url} for {speaker_schedule_new}"
        template.save()
        room = RoomFactory(event=event)
        submission = _scheduled_submission(event, room)
        submission.speakers.add(SpeakerFactory(event=event))
        TalkSlotFactory(
            submission=None,
            schedule=event.wip_schedule,
            room=room,
            start=event.datetime_from + dt.timedelta(hours=2),
            end=event.datetime_from + dt.timedelta(hours=3),
            slot_type=SlotType.BREAK,
            description="Coffee Break",
        )
    client.force_login(user)

    response = client.get(event.orga_urls.release_schedule)

    assert response.status_code == 200
    body = response.content.decode()
    assert "cannot be notified" not in body
    assert "only work with a pretalx account" not in body


def test_schedule_toggle_flips_visibility(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(event.orga_urls.toggle_schedule, follow=True)

    assert response.status_code == 200
    updated = Event.objects.get(pk=event.pk)
    assert updated.feature_flags["show_schedule"] is False

    response = client.post(event.orga_urls.toggle_schedule, follow=True)

    assert response.status_code == 200
    updated = Event.objects.get(pk=event.pk)
    assert updated.feature_flags["show_schedule"] is True


def test_schedule_resend_mails(client, talk_slot):
    event = talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        initial_mail_count = event.queued_mails.count()
        title = talk_slot.submission.title
        room_name = str(talk_slot.room.name)
    client.force_login(user)

    response = client.post(event.orga_urls.schedule + "resend_mails", follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert event.queued_mails.count() == initial_mail_count
        freeze_schedule(talk_slot.schedule, "v1", notify_speakers=False)

    response = client.post(event.orga_urls.schedule + "resend_mails", follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert event.queued_mails.count() == initial_mail_count + 1
        mail = event.queued_mails.last()
        assert title in mail.text
        assert room_name in mail.text
        assert mail.submissions.count() == 1


@pytest.mark.parametrize("item_count", (1, 3))
def test_talk_list_returns_talks_json(
    client, event, item_count, django_assert_num_queries
):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        for _ in range(item_count):
            speaker = SpeakerFactory(event=event)
            sub = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
            sub.speakers.add(speaker)
            TalkSlotFactory(submission=sub, is_visible=True)
    client.force_login(user)

    with django_assert_num_queries(8):
        response = client.get(event.orga_urls.talks_api)

    assert response.status_code == 200
    data = response.json()
    assert "talks" in data
    assert len(data["talks"]) == item_count
    assert data["talks"][0]["title"]


def test_talk_list_with_version_and_warnings_parameters(client, published_talk_slot):
    event = published_talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(event.orga_urls.talks_api + "?warnings=true")
    assert response.status_code == 200
    assert response.json()["warnings"] == {}

    response = client.get(event.orga_urls.talks_api + "?version=v1")
    assert response.status_code == 200
    data = response.json()
    assert [talk["title"] for talk in data["talks"]] == [
        str(published_talk_slot.submission.title)
    ]


def test_talk_list_create_slots(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        room = RoomFactory(event=event)
        hidden = RoomFactory(event=event, hidden=True)
        initial_count = event.wip_schedule.talks.count()
    client.force_login(user)

    def create(payload):
        return client.post(
            event.orga_urls.talks_api,
            data=json.dumps(payload),
            content_type="application/json",
        )

    for room_data in ({"room": hidden.pk}, {"room": 123456}, {}):
        response = create({"duration": 45, "title": "Coffee Break", **room_data})
        assert response.status_code == 400, room_data
        assert response.json()["error"] == "Room unavailable."
    with scopes_disabled():
        assert event.wip_schedule.talks.count() == initial_count

    response = create({"room": room.pk, "duration": 45, "title": "Coffee Break"})
    assert response.status_code == 200
    assert response.json()["duration"] == 45
    with scopes_disabled():
        slot = (
            event.wip_schedule.talks.select_related("room")
            .filter(submission__isnull=True)
            .get()
        )
        assert str(slot.description) == "Coffee Break"
        assert slot.room == room

    response = create(
        {"room": room.pk, "duration": 30, "title": "Blocked", "slot_type": "blocker"}
    )
    assert response.status_code == 200
    assert response.json()["slot_type"] == "blocker"

    response = create({"room": room.pk, "slot_type": "invalid_type"})
    assert response.status_code == 200
    assert response.json()["slot_type"] == "break"
    with scopes_disabled():
        assert event.wip_schedule.talks.count() == initial_count + 3


def test_talk_update_patch_and_delete_submission_slot(client, talk_slot):
    event = talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        hidden_room = RoomFactory(event=event, hidden=True)
        room = talk_slot.room
        title = str(talk_slot.submission.title)
        duration = talk_slot.submission.get_duration()
        initial_count = event.wip_schedule.talks.count()
        new_start = event.datetime_from + dt.timedelta(hours=2)
    client.force_login(user)
    url = f"{event.orga_urls.schedule_api}talks/{talk_slot.pk}/"

    def patch(url, payload):
        return client.patch(
            url, data=json.dumps(payload), content_type="application/json"
        )

    response = patch(
        f"{event.orga_urls.schedule_api}talks/999999/",
        {"start": "2024-01-01T10:00:00Z"},
    )
    assert response.status_code == 404

    for room_pk in (hidden_room.pk, 123456):
        response = patch(
            url, {"room": room_pk, "start": event.datetime_from.isoformat()}
        )
        assert response.status_code == 400
        assert response.json()["error"] == "Room unavailable."
        talk_slot.refresh_from_db()
        assert talk_slot.room_id == room.pk

    response = patch(url, {"start": new_start.isoformat(), "room": room.pk})
    assert response.status_code == 200
    assert response.json()["title"] == title
    with scopes_disabled():
        talk_slot.refresh_from_db()
        assert talk_slot.start == new_start
        assert talk_slot.end == new_start + dt.timedelta(minutes=duration)
        assert talk_slot.room_id == room.pk

    for room_data in ({"room": None}, {}):
        later_start = new_start + dt.timedelta(hours=1)
        response = patch(url, {"start": later_start.isoformat(), **room_data})
        assert response.status_code == 200
        with scopes_disabled():
            talk_slot.refresh_from_db()
            assert talk_slot.start == later_start
            assert talk_slot.room_id == room.pk

    response = patch(url, {})
    assert response.status_code == 200
    with scopes_disabled():
        talk_slot.refresh_from_db()
        assert talk_slot.start is None
        assert talk_slot.end is None
        assert talk_slot.room is None

    response = client.delete(url)
    assert response.status_code == 200
    assert "error" in response.json()
    with scopes_disabled():
        assert event.wip_schedule.talks.count() == initial_count

    response = client.delete(f"{event.orga_urls.schedule_api}talks/999999/")
    assert response.status_code == 404


def test_talk_update_patch_and_delete_break_slot(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        room = RoomFactory(event=event)
        slot = TalkSlotFactory(
            submission=None, schedule=event.wip_schedule, room=room, is_visible=True
        )
        slot_pk = slot.pk
        new_start = event.datetime_from + dt.timedelta(hours=1)
    client.force_login(user)
    url = f"{event.orga_urls.schedule_api}talks/{slot.pk}/"

    def patch(payload):
        return client.patch(
            url, data=json.dumps(payload), content_type="application/json"
        )

    response = patch(
        {
            "start": new_start.isoformat(),
            "room": room.pk,
            "duration": 90,
            "title": "Long Break",
        }
    )
    assert response.status_code == 200
    with scopes_disabled():
        slot.refresh_from_db()
        assert slot.duration == 90
        assert str(slot.description) == "Long Break"
        assert slot.start == new_start

    response = patch(
        {
            "start": new_start.isoformat(),
            "end": (new_start + dt.timedelta(minutes=60)).isoformat(),
            "room": room.pk,
        }
    )
    assert response.status_code == 200
    with scopes_disabled():
        slot.refresh_from_db()
        assert slot.duration == 60

    later_start = new_start + dt.timedelta(hours=2)
    response = patch({"start": later_start.isoformat(), "room": room.pk})
    assert response.status_code == 200
    with scopes_disabled():
        slot.refresh_from_db()
        assert slot.start == later_start
        assert slot.duration == 60

    response = client.delete(url)
    assert response.status_code == 200
    assert response.json()["success"] is True
    with scopes_disabled():
        assert not TalkSlot.objects.filter(pk=slot_pk).exists()


def test_schedule_warnings_reports_room_overlap(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        room = RoomFactory(event=event)
        submissions = []
        for _ in range(2):
            submission = _scheduled_submission(event, room)
            submission.speakers.add(SpeakerFactory(event=event))
            submissions.append(submission)
    client.force_login(user)

    response = client.get(event.orga_urls.schedule_api + "warnings/")

    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) == {submission.code for submission in submissions}
    assert all(
        [warning["type"] for warning in warnings] == ["room_overlap"]
        for warnings in data.values()
    )


def test_schedule_availabilities(client, event):
    day_start = event.datetime_from
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        visible = RoomFactory(event=event)
        hidden = RoomFactory(event=event, hidden=True)
        AvailabilityFactory(event=event, room=visible)
        AvailabilityFactory(event=event, room=hidden)

        speaker = SpeakerFactory(event=event)
        AvailabilityFactory(event=event, person=speaker)
        single = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        single.speakers.add(speaker)
        single_slot = TalkSlotFactory(submission=single, is_visible=True)

        speaker1 = SpeakerFactory(event=event)
        speaker2 = SpeakerFactory(event=event)
        AvailabilityFactory(
            event=event,
            person=speaker1,
            start=day_start + dt.timedelta(hours=8),
            end=day_start + dt.timedelta(hours=16),
        )
        AvailabilityFactory(
            event=event,
            person=speaker2,
            start=day_start + dt.timedelta(hours=12),
            end=day_start + dt.timedelta(hours=20),
        )
        shared = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        shared.speakers.add(speaker1, speaker2)
        shared_slot = TalkSlotFactory(submission=shared, is_visible=True)

        unavailable = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        unavailable.speakers.add(
            SpeakerFactory(event=event), SpeakerFactory(event=event)
        )
        unavailable_slot = TalkSlotFactory(submission=unavailable, is_visible=True)
    client.force_login(user)

    response = client.get(event.orga_urls.schedule_api + "availabilities/")

    assert response.status_code == 200
    data = response.json()
    assert str(visible.pk) in data["rooms"]
    assert str(hidden.pk) not in data["rooms"]
    assert len(data["rooms"][str(visible.pk)]) == 1
    assert len(data["talks"][str(single_slot.pk)]) == 1
    assert [
        (
            dt.datetime.fromisoformat(window["start"]),
            dt.datetime.fromisoformat(window["end"]),
        )
        for window in data["talks"][str(shared_slot.pk)]
    ] == [(day_start + dt.timedelta(hours=12), day_start + dt.timedelta(hours=16))]
    assert data["talks"][str(unavailable_slot.pk)] == []


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
        assert talk_slot.room_id == room.pk
        assert talk_slot.start.date() == event.date_from


@pytest.mark.parametrize(
    ("action", "needs_settings_permission"),
    (("list", False), ("create", True), ("update", True), ("delete", True)),
)
@pytest.mark.parametrize(
    "role", ("anonymous", "unrelated", "submissions_only", "event_settings")
)
def test_room_views_permissions(client, event, action, needs_settings_permission, role):
    with scopes_disabled():
        room = RoomFactory(event=event, name="Attic")
        match role:
            case "unrelated":
                user = UserFactory()
            case "anonymous":
                user = None
            case _:
                user = make_orga_user(
                    event, can_change_event_settings=(role == "event_settings")
                )
    url = {
        "list": event.orga_urls.room_settings,
        "create": event.orga_urls.new_room,
        "update": room.urls.edit,
        "delete": room.urls.delete,
    }[action]
    if user:
        client.force_login(user)

    response = client.get(url)

    if role == "anonymous":
        assert response.status_code == 302
        assert "/login/" in response.url
        return
    if role == "unrelated" or (needs_settings_permission and role != "event_settings"):
        assert response.status_code == 404
        assert "Attic" not in response.content.decode()
    else:
        assert response.status_code == 200
        assert ("Attic" in response.content.decode()) is (action != "create")


@pytest.mark.parametrize("item_count", (1, 3))
def test_room_list_shows_rooms(client, event, item_count, django_assert_num_queries):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        rooms = RoomFactory.create_batch(item_count, event=event)
    client.force_login(user)

    with django_assert_num_queries(14):
        response = client.get(event.orga_urls.room_settings)

    assert response.status_code == 200
    content = response.content.decode()
    assert all(str(room.name) in content for room in rooms)
    assert "dragsort-url=" in content
    assert all(f'dragsort-id="{room.pk}"' in content for room in rooms)


def test_room_create_update_hide_and_delete(client, event):
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
        room = event.rooms.get()
        assert str(room.name) == "Workshop Room"
        assert room.availabilities.count() == 1
        Room.objects.filter(pk=room.pk).update(guid=None)
        historic = Schedule.objects.create(event=event, version="v0")
        TalkSlotFactory(submission=None, room=room, schedule=historic)

    response = client.get(room.urls.settings_base)
    assert response.status_code == 200
    content = response.content.decode()
    assert "This room is currently hidden" not in content
    assert room.urls.unhide not in content

    response = client.post(
        room.urls.edit,
        data={
            "name_0": "Attic",
            "guid": str(uuid4()),
            "availabilities": json.dumps({"availabilities": []}),
        },
        follow=True,
    )
    assert response.status_code == 200
    with scopes_disabled():
        room.refresh_from_db(fields=["name", "guid"])
        assert str(room.name) == "Attic"
        assert room.availabilities.count() == 0
        action = room.logged_actions().get(action_type="pretalx.room.update")
        assert action.data["changes"]["guid"]["new"]
        assert not action.data["changes"]["guid"]["old"]
        assert action.data["changes"]["name"]["new"] == {"en": "Attic"}

    response = client.get(room.urls.hide)
    assert response.status_code == 200
    assert "Attic" in response.content.decode()

    response = client.post(room.urls.hide, follow=True)
    assert response.status_code == 200
    room.refresh_from_db(fields=["hidden"])
    assert room.hidden is True
    with scopes_disabled():
        assert room.logged_actions().filter(action_type="pretalx.room.hide").exists()

    response = client.get(room.urls.settings_base)
    assert response.status_code == 200
    content = response.content.decode()
    assert "This room is currently hidden" in content
    assert room.urls.unhide in content

    response = client.get(room.urls.unhide)
    assert response.status_code == 200
    assert "Attic" in response.content.decode()

    response = client.post(room.urls.unhide, follow=True)
    assert response.status_code == 200
    room.refresh_from_db(fields=["hidden", "position"])
    assert room.hidden is False
    with scopes_disabled():
        assert room.logged_actions().filter(action_type="pretalx.room.unhide").exists()

    response = client.post(room.urls.delete, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert Room.objects.filter(pk=room.pk).exists()
        TalkSlot.objects.filter(schedule=historic).delete()

    response = client.get(room.urls.delete)
    assert response.status_code == 200

    response = client.post(room.urls.delete, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert not Room.objects.filter(pk=room.pk).exists()


@pytest.mark.parametrize(
    ("initial_capacity", "new_capacity", "expect_warning"),
    ((200, 3, True), (2, 2, False)),
    ids=("decrease_below_signups", "unchanged"),
)
def test_room_update_capacity_warns_when_below_signup_count(
    client, event, initial_capacity, new_capacity, expect_warning
):
    event.feature_flags["attendee_signup"] = True
    event.save()
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        room = RoomFactory(event=event, capacity=initial_capacity)
        sub_type = event.cfp.default_type
        sub_type.attendee_signup_required = True
        sub_type.save()
        submission = SubmissionFactory(
            event=event, state=SubmissionStates.CONFIRMED, submission_type=sub_type
        )
        TalkSlotFactory(
            submission=submission,
            schedule=event.wip_schedule,
            room=room,
            start=event.datetime_from,
            end=event.datetime_from + dt.timedelta(hours=1),
        )
        for _ in range(5):
            AttendeeSignupFactory(submission=submission)
    client.force_login(user)

    response = client.post(
        room.urls.edit,
        data={
            "name_0": str(room.name),
            "guid": "",
            "capacity": str(new_capacity),
            "availabilities": json.dumps({"availabilities": []}),
        },
        follow=True,
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert ("now has more signed-up attendees" in content) is expect_warning
    with scopes_disabled():
        room.refresh_from_db()
        assert room.capacity == new_capacity


def test_room_in_use_cannot_be_deleted_or_hidden(client, talk_slot):
    event = talk_slot.submission.event
    room = talk_slot.room
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(room.urls.delete, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        assert Room.objects.filter(pk=room.pk).exists()

    response = client.post(room.urls.hide, follow=True)
    assert response.status_code == 200
    room.refresh_from_db(fields=["hidden"])
    assert room.hidden is False
    messages = [
        (message.level, str(message.message))
        for message in get_messages(response.wsgi_request)
    ]
    assert messages[0][0] == message_constants.ERROR
    assert "neither be deleted nor hidden" in messages[0][1]


def test_room_visibility_requires_settings_permission(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=False)
        visible = RoomFactory(event=event, hidden=False)
        hidden = RoomFactory(event=event, hidden=True)
    client.force_login(user)

    response = client.post(visible.urls.hide)
    assert response.status_code == 404
    visible.refresh_from_db(fields=["hidden"])
    assert visible.hidden is False

    response = client.post(hidden.urls.unhide)
    assert response.status_code == 404
    hidden.refresh_from_db(fields=["hidden"])
    assert hidden.hidden is True


def test_schedule_view_with_all_rooms_hidden_shows_configure_notice(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_submissions=True)
        RoomFactory(event=event, hidden=True)
    client.force_login(user)

    response = client.get(event.orga_urls.schedule)

    assert response.status_code == 200
    content = response.content.decode()
    assert "once you have configured some rooms" in content
    assert 'id="app"' not in content


def test_schedule_export(client, event):
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
    data = {"title": "on", "speaker_ids": "on", f"question_{question.id}": "on"}

    response = client.post(
        event.orga_urls.schedule_export,
        data={"target": "rejected", "title": "on", "export_format": "json"},
    )
    assert response.status_code == 302
    assert response.url == event.orga_urls.schedule_export
    messages = list(get_messages(response.wsgi_request))
    assert [message.level for message in messages] == [message_constants.WARNING]
    assert str(messages[0]) == "No data to be exported"

    response = client.post(
        event.orga_urls.schedule_export,
        data={**data, "target": "all", "export_format": "csv"},
    )
    assert response.status_code == 200
    assert "<!doctype" in response.content.decode().strip().lower()

    response = client.post(
        event.orga_urls.schedule_export,
        data={
            **data,
            "target": "all",
            "export_format": "csv",
            "data_delimiter": "comma",
        },
    )
    assert response.status_code == 200
    # CSV exports start with a UTF-8 BOM so Excel detects the encoding.
    assert response.content.decode("utf-8-sig") == (
        f"ID,Proposal title,Speaker IDs,Dietary needs\r\n"
        f"{submission.code},{submission.title},{speaker.code},Vegan\r\n"
    )
    assert response.content.startswith(b"\xef\xbb\xbf")

    response = client.post(
        event.orga_urls.schedule_export,
        data={**data, "target": "all", "export_format": "json"},
    )
    assert response.status_code == 200
    assert json.loads(response.content.decode()) == [
        {
            "ID": submission.code,
            "Proposal title": submission.title,
            "Speaker IDs": [speaker.code],
            "Dietary needs": "Vegan",
        }
    ]


def test_schedule_export_trigger(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.post(event.orga_urls.schedule_export_trigger)
    assert response.status_code == 302
    assert response.url == event.orga_urls.schedule_export_download

    with scopes_disabled():
        cached_file = CachedFileFactory()
        event.cache.set("schedule_export_cached_file", str(cached_file.id), None)

    response = client.post(event.orga_urls.schedule_export_trigger)
    assert response.status_code == 302
    with scopes_disabled():
        assert not CachedFile.objects.filter(id=cached_file.id).exists()
        assert event.cache.get("schedule_export_cached_file") is None


def test_schedule_export_download(client, published_talk_slot):
    event = published_talk_slot.submission.event
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
    client.force_login(user)

    response = client.get(
        event.orga_urls.schedule_export_download, data={"cached_file": "nonexistent"}
    )
    assert response.status_code == 302
    assert response.url == event.orga_urls.schedule_export
    messages = list(get_messages(response.wsgi_request))
    assert [message.level for message in messages] == [message_constants.ERROR]

    response = client.get(event.orga_urls.schedule_export_download, follow=True)
    assert response.status_code == 200
    with scopes_disabled():
        filenames = list(CachedFile.objects.values_list("filename", flat=True))
    assert filenames == [f"{event.slug}_schedule.zip"]

    with scopes_disabled():
        stale_file = CachedFileFactory()
    fresh_event = Event.objects.get(pk=event.pk)
    fresh_event.cache.set("schedule_export_cached_file", str(stale_file.id), None)
    assert fresh_event.cache.get("schedule_export_cached_file") == str(stale_file.id)

    response = client.get(event.orga_urls.schedule_export_download, follow=True)
    assert response.status_code == 200


def test_schedule_export_download_serves_cached_file(client, event):
    with scopes_disabled():
        user = make_orga_user(event, can_change_event_settings=True)
        cached_file = CachedFileFactory(session_key="somebody-elses-session")
        cached_file.file.save("test.zip", ContentFile(b"fake zip content"))
        event.cache.set("schedule_export_cached_file", str(cached_file.id), None)
    client.force_login(user)

    response = client.get(event.orga_urls.schedule_export_download)

    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"


def test_talk_update_patch_returns_signup_warning(client, event):
    # The PATCH response must surface the signup-capacity warning so the
    # editor's warning icon stays put after a drag, matching what
    # ``get_all_talk_warnings`` produces on initial load.
    with scopes_disabled():
        event.feature_flags["attendee_signup"] = True
        event.save()
        sub_type = event.cfp.default_type
        sub_type.attendee_signup_required = True
        sub_type.save()
        user = make_orga_user(event, can_change_submissions=True)
        room = RoomFactory(event=event, capacity=10)
        submission = SubmissionFactory(
            event=event,
            state=SubmissionStates.CONFIRMED,
            submission_type=sub_type,
            attendee_signup_capacity=80,
        )
        slot = TalkSlotFactory(
            submission=submission,
            schedule=event.wip_schedule,
            room=room,
            start=event.datetime_from,
            end=event.datetime_from + dt.timedelta(hours=1),
        )
        new_start = event.datetime_from + dt.timedelta(hours=2)
    client.force_login(user)

    response = client.patch(
        f"{event.orga_urls.schedule_api}talks/{slot.pk}/",
        data=json.dumps({"start": new_start.isoformat(), "room": room.pk}),
        content_type="application/json",
    )

    assert response.status_code == 200
    types = [w["type"] for w in response.json()["warnings"]]
    assert "signup_room_too_small" in types
