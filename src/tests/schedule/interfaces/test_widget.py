# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils.timezone import now as tz_now
from django_scopes import scope

from pretalx.schedule.domain.release import freeze_schedule
from pretalx.schedule.interfaces.widget import build_widget_data
from pretalx.schedule.models.slot import SlotType
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    AttendeeSignupFactory,
    EventFactory,
    RoomFactory,
    SpeakerFactory,
    SubmissionFactory,
    TagFactory,
    TalkSlotFactory,
    TrackFactory,
)
from tests.utils import refresh

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_build_widget_data_talk_with_track_and_speaker(event):
    track = TrackFactory(event=event)
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(
        event=event,
        state=SubmissionStates.CONFIRMED,
        content_locale="de-formal",
        track=track,
    )
    submission.speakers.add(speaker)
    with scope(event=event):
        schedule = event.wip_schedule
    slot = TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
        is_visible=True,
    )

    with scope(event=event):
        data = build_widget_data(schedule)
        future = build_widget_data(
            schedule, filter_updated=tz_now() + dt.timedelta(hours=1)
        )
        event.cfp.fields["do_not_record"] = {"visibility": "do_not_ask"}
        event.cfp.save()
        without_do_not_record = build_widget_data(schedule)
    room = refresh(room)

    assert data == {
        "version": None,
        "schedule_id": schedule.pk,
        "timezone": event.timezone,
        "event_start": event.date_from.isoformat(),
        "event_end": event.date_to.isoformat(),
        "talks": [
            {
                "code": submission.code,
                "id": slot.id,
                "title": submission.title,
                "abstract": submission.abstract,
                "speakers": [speaker.code],
                "track": track.id,
                "start": slot.local_start,
                "end": slot.local_end,
                "room": room.id,
                "duration": submission.get_duration(),
                "updated": slot.updated.isoformat(),
                "content_locale": "de-formal",
                "content_lang": "de",
                "do_not_record": False,
                "tags": [],
            }
        ],
        "tags": [],
        "tracks": [
            {
                "id": track.id,
                "name": track.name,
                "description": track.description,
                "color": track.color,
            }
        ],
        "rooms": [{"id": room.id, "name": room.name, "description": room.description}],
        "speakers": [
            {
                "code": speaker.code,
                "name": speaker.get_display_name(),
                "avatar": None,
                "avatar_thumbnail_default": None,
                "avatar_thumbnail_tiny": None,
            }
        ],
    }
    assert future["talks"] == []
    assert "do_not_record" not in without_do_not_record["talks"][0]


def test_build_widget_data_invisible_talk_only_with_all_talks(event):
    room = RoomFactory(event=event)
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
        is_visible=False,
    )

    with scope(event=event):
        default = build_widget_data(schedule)
        all_talks = build_widget_data(schedule, all_talks=True)

    assert default["talks"] == []
    assert [(talk["code"], talk["state"]) for talk in all_talks["talks"]] == [
        (submission.code, submission.state)
    ]


def test_build_widget_data_breaks_and_blockers(event):
    room = RoomFactory(event=event)
    with scope(event=event):
        schedule = event.wip_schedule
    start = event.datetime_from
    end = start + dt.timedelta(hours=1)
    break_slot = TalkSlotFactory(
        submission=None,
        schedule=schedule,
        room=room,
        slot_type=SlotType.BREAK,
        is_visible=True,
        description="Lunch",
        start=start,
        end=end,
    )
    blocker = TalkSlotFactory(
        submission=None,
        schedule=schedule,
        room=room,
        slot_type=SlotType.BLOCKER,
        is_visible=True,
        start=start,
        end=end,
    )

    with scope(event=event):
        default = build_widget_data(schedule)
        with_blockers = build_widget_data(schedule, include_blockers=True)

    assert default["talks"] == [
        {
            "id": break_slot.id,
            "title": "Lunch",
            "start": start,
            "end": break_slot.local_end,
            "room": room.id,
            "slot_type": SlotType.BREAK,
        }
    ]
    assert {(talk["id"], talk["slot_type"]) for talk in with_blockers["talks"]} == {
        (break_slot.id, SlotType.BREAK),
        (blocker.id, SlotType.BLOCKER),
    }


def test_build_widget_data_rooms(event):
    room = RoomFactory(event=event)
    unused = RoomFactory(event=event)
    hidden = RoomFactory(event=event, hidden=True)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )

    with scope(event=event):
        used_rooms = build_widget_data(schedule)["rooms"]
        all_rooms = build_widget_data(schedule, all_rooms=True)["rooms"]
        freeze_schedule(schedule, "v1", notify_speakers=False)
        room.hidden = True
        room.save()
        released = build_widget_data(schedule)

    assert [r["id"] for r in used_rooms] == [room.id]
    assert [r["id"] for r in all_rooms] == [room.id, unused.id]
    assert hidden.id not in [r["id"] for r in all_rooms]
    assert released["talks"][0]["room"] == room.id
    assert [r["id"] for r in released["rooms"]] == [room.id]


def test_build_widget_data_roomless_talk_and_skipped_zero_duration(event):
    room = RoomFactory(event=event)
    roomless = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    zero_duration = SubmissionFactory(
        event=event, state=SubmissionStates.CONFIRMED, duration=0
    )
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(
        submission=roomless,
        schedule=schedule,
        room=None,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
        is_visible=True,
    )
    TalkSlotFactory(
        submission=zero_duration,
        schedule=schedule,
        room=room,
        start=None,
        end=None,
        is_visible=True,
    )

    with scope(event=event):
        data = build_widget_data(schedule)

    assert [(talk["code"], talk["room"]) for talk in data["talks"]] == [
        (roomless.code, None)
    ]
    assert [r["id"] for r in data["rooms"]] == [room.id]


def test_build_widget_data_tags_only_public_tags_of_included_talks(event):
    room = RoomFactory(event=event)
    beginner = TagFactory(event=event, tag="Beginner", color="#00ff00", is_public=True)
    advanced = TagFactory(event=event, tag="advanced", color="#0000ff", is_public=True)
    internal = TagFactory(event=event, tag="internal", is_public=False)
    hidden_only = TagFactory(event=event, tag="Hidden only", is_public=True)
    TagFactory(event=event, tag="Unused", is_public=True)
    tagged = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    tagged.tags.add(beginner, advanced, internal)
    untagged = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    untagged.tags.add(internal)
    invisible = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    invisible.tags.add(hidden_only, beginner)
    with scope(event=event):
        schedule = event.wip_schedule
    for submission, is_visible, hours in (
        (tagged, True, 0),
        (untagged, True, 1),
        (invisible, False, 2),
    ):
        TalkSlotFactory(
            submission=submission,
            schedule=schedule,
            room=room,
            start=event.datetime_from + dt.timedelta(hours=hours),
            end=event.datetime_from + dt.timedelta(hours=hours + 1),
            is_visible=is_visible,
        )

    with scope(event=event):
        data = build_widget_data(schedule)
        all_talks = build_widget_data(schedule, all_talks=True)

    assert [(talk["code"], talk["tags"]) for talk in data["talks"]] == [
        (tagged.code, [advanced.pk, beginner.pk]),
        (untagged.code, []),
    ]
    assert data["tags"] == [
        {"id": advanced.pk, "name": "advanced", "color": "#0000ff"},
        {"id": beginner.pk, "name": "Beginner", "color": "#00ff00"},
    ]
    assert [tag["id"] for tag in all_talks["tags"]] == [
        advanced.pk,
        beginner.pk,
        hidden_only.pk,
    ]


@pytest.mark.parametrize(
    ("feature_on", "signup_required", "room_capacity", "signup_count", "expected"),
    (
        (True, True, 20, 0, "open"),
        (True, True, 2, 2, "full"),
        (True, False, 20, 0, None),  # non-signup session on signup event
        (False, True, 20, 0, "__missing__"),  # feature off omits the key entirely
    ),
)
def test_build_widget_data_signup_status(
    feature_on, signup_required, room_capacity, signup_count, expected
):
    event = EventFactory(feature_flags={"attendee_signup": feature_on})
    sub_type = event.cfp.default_type
    sub_type.attendee_signup_required = signup_required
    sub_type.save()
    room = RoomFactory(event=event, capacity=room_capacity)
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.CONFIRMED, submission_type=sub_type
    )
    with scope(event=event):
        schedule = event.wip_schedule
        TalkSlotFactory(
            submission=submission,
            schedule=schedule,
            room=room,
            start=event.datetime_from,
            end=event.datetime_from + dt.timedelta(hours=1),
            is_visible=True,
        )
        for _ in range(signup_count):
            AttendeeSignupFactory(submission=submission)
        data = build_widget_data(schedule)

    assert data["talks"][0].get("signup_status", "__missing__") == expected
