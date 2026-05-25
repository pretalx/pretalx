# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils.timezone import now as tz_now
from django_scopes import scope

from pretalx.schedule.interfaces.widget import build_widget_data
from pretalx.schedule.models.slot import SlotType
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    AttendeeSignupFactory,
    EventFactory,
    RoomFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TrackFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_build_widget_data_basic(event):
    room = RoomFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
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

    with scope(event=event):
        data = build_widget_data(schedule)

    assert data["version"] is None
    assert data["schedule_id"] == schedule.pk
    assert data["event_start"] == event.date_from.isoformat()
    assert data["event_end"] == event.date_to.isoformat()
    assert len(data["talks"]) == 1
    assert data["talks"][0]["code"] == submission.code
    assert len(data["rooms"]) == 1
    assert data["rooms"][0]["id"] == room.id


def test_build_widget_data_excludes_invisible_by_default(event):
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
        data = build_widget_data(schedule)

    assert len(data["talks"]) == 0


def test_build_widget_data_all_talks_includes_invisible(event):
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
        data = build_widget_data(schedule, all_talks=True)

    assert len(data["talks"]) == 1
    assert data["talks"][0]["state"] == submission.state


@pytest.mark.parametrize(
    ("include_blockers", "expected_count"),
    ((False, 0), (True, 1)),
    ids=["excluded_by_default", "included_when_requested"],
)
def test_build_widget_data_blockers(event, include_blockers, expected_count):
    room = RoomFactory(event=event)
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(
        submission=None,
        schedule=schedule,
        room=room,
        slot_type=SlotType.BLOCKER,
        is_visible=True,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )

    with scope(event=event):
        data = build_widget_data(schedule, include_blockers=include_blockers)

    assert len(data["talks"]) == expected_count


def test_build_widget_data_break_slot(event):
    room = RoomFactory(event=event)
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(
        submission=None,
        schedule=schedule,
        room=room,
        slot_type=SlotType.BREAK,
        is_visible=True,
        description="Lunch",
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )

    with scope(event=event):
        data = build_widget_data(schedule)

    assert len(data["talks"]) == 1
    assert data["talks"][0]["slot_type"] == SlotType.BREAK
    assert "code" not in data["talks"][0]


def test_build_widget_data_includes_tracks(event):
    track = TrackFactory(event=event)
    room = RoomFactory(event=event)
    submission = SubmissionFactory(event=event, track=track)
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

    with scope(event=event):
        data = build_widget_data(schedule)

    assert len(data["tracks"]) == 1
    assert data["tracks"][0]["id"] == track.id
    assert data["tracks"][0]["color"] == track.color


def test_build_widget_data_includes_speakers(event):
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
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

    with scope(event=event):
        data = build_widget_data(schedule)

    assert len(data["speakers"]) == 1
    assert data["speakers"][0]["code"] == speaker.code


def test_build_widget_data_all_rooms(event):
    room1 = RoomFactory(event=event)
    room2 = RoomFactory(event=event)
    with scope(event=event):
        schedule = event.wip_schedule
        data = build_widget_data(schedule, all_rooms=True)

    room_ids = {r["id"] for r in data["rooms"]}
    assert room1.id in room_ids
    assert room2.id in room_ids


def test_build_widget_data_filter_updated(event):
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
        is_visible=True,
    )

    future = tz_now() + dt.timedelta(hours=1)
    with scope(event=event):
        data = build_widget_data(schedule, filter_updated=future)

    assert len(data["talks"]) == 0


def test_build_widget_data_includes_talk_without_room(event):
    """Slots with a submission but no assigned room are still emitted; their
    room id is just ``None`` and they don't contribute to the rooms list."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=None,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
        is_visible=True,
    )

    with scope(event=event):
        data = build_widget_data(schedule)

    assert len(data["talks"]) == 1
    assert data["talks"][0]["code"] == submission.code
    assert data["talks"][0]["room"] is None
    assert data["rooms"] == []


def test_build_widget_data_skips_zero_duration_without_times(event):
    """Slots whose submission has zero duration and no start/end are excluded."""
    room = RoomFactory(event=event)
    submission = SubmissionFactory(
        event=event, state=SubmissionStates.CONFIRMED, duration=0
    )
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=None,
        end=None,
        is_visible=True,
    )

    with scope(event=event):
        data = build_widget_data(schedule)

    assert len(data["talks"]) == 0


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

    if expected == "__missing__":
        assert "signup_status" not in data["talks"][0]
    else:
        assert data["talks"][0]["signup_status"] == expected


def test_build_widget_data_omits_do_not_record_when_not_requested(event):
    event.cfp.fields["do_not_record"] = {"visibility": "do_not_ask"}
    event.cfp.save()
    room = RoomFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
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

    with scope(event=event):
        data = build_widget_data(schedule)

    assert "do_not_record" not in data["talks"][0]
