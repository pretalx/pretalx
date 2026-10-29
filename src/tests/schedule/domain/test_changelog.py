# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils.timezone import now

from pretalx.schedule.domain.changelog import build_changelog
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    RoomFactory,
    ScheduleFactory,
    SubmissionFactory,
    TalkSlotFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_build_changelog_lists_released_schedules_newest_first(event):
    assert build_changelog(event) == []

    ScheduleFactory(event=event, version=None, published=None)
    v1 = ScheduleFactory(
        event=event, version="v1", published=now() - dt.timedelta(hours=2)
    )
    v2 = ScheduleFactory(
        event=event, version="v2", published=now() - dt.timedelta(hours=1)
    )

    result = build_changelog(event)

    assert result == [v2, v1]
    assert result[0].previous_schedule == v1
    assert result[1].previous_schedule is None


def test_build_changelog_batches_visible_scheduled_talks(
    event, django_assert_num_queries
):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    room = RoomFactory(event=event)
    start = event.datetime_from
    end = start + dt.timedelta(hours=1)
    v1 = ScheduleFactory(
        event=event, version="v1", published=now() - dt.timedelta(hours=2)
    )
    v2 = ScheduleFactory(
        event=event, version="v2", published=now() - dt.timedelta(hours=1)
    )
    slot_v1 = TalkSlotFactory(
        schedule=v1, submission=submission, room=room, start=start, end=end
    )
    slot_v2 = TalkSlotFactory(
        schedule=v2, submission=submission, room=room, start=start, end=end
    )
    TalkSlotFactory(
        schedule=v2,
        submission=submission,
        room=room,
        start=start,
        end=end,
        is_visible=False,
    )
    TalkSlotFactory(schedule=v2, submission=submission, room=None, start=start, end=end)
    TalkSlotFactory(schedule=v2, submission=submission, room=room, start=None, end=None)

    # 1 query for schedules, 1 for slots, 1 for rooms, 1 for submissions,
    # 1 for the speakers prefetch.
    with django_assert_num_queries(5):
        result = build_changelog(event)
        talks = [
            [(slot, slot.submission, slot.room) for slot in schedule.scheduled_talks]
            for schedule in result
        ]

    assert talks == [[(slot_v2, submission, room)], [(slot_v1, submission, room)]]


def test_build_changelog_limit_returns_newest_schedules(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    room = RoomFactory(event=event)
    for index, version in enumerate(("v1", "v2", "v3", "v4")):
        schedule = ScheduleFactory(
            event=event,
            version=version,
            published=now() - dt.timedelta(hours=10 - index),
        )
        TalkSlotFactory(
            schedule=schedule,
            submission=submission,
            room=room,
            start=event.datetime_from,
            end=event.datetime_from + dt.timedelta(hours=1),
        )

    result = build_changelog(event, limit=2)

    assert [schedule.version for schedule in result] == ["v4", "v3"]
    assert result[-1].previous_schedule.version == "v2"
    assert len(result[-1].previous_schedule.scheduled_talks) == 1


def test_build_changelog_computes_changes_without_n_plus_one(
    event, django_assert_num_queries
):
    sub_a = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    sub_b = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    sub_c = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    room_1 = RoomFactory(event=event)
    room_2 = RoomFactory(event=event)
    start = event.datetime_from
    hour = dt.timedelta(hours=1)
    v1 = ScheduleFactory(
        event=event, version="v1", published=now() - dt.timedelta(hours=2)
    )
    TalkSlotFactory(
        schedule=v1, submission=sub_a, room=room_1, start=start, end=start + hour
    )
    TalkSlotFactory(
        schedule=v1,
        submission=sub_c,
        room=room_2,
        start=start + hour,
        end=start + 2 * hour,
    )
    v2 = ScheduleFactory(
        event=event, version="v2", published=now() - dt.timedelta(hours=1)
    )
    TalkSlotFactory(
        schedule=v2,
        submission=sub_a,
        room=room_2,
        start=start + 2 * hour,
        end=start + 3 * hour,
    )
    TalkSlotFactory(
        schedule=v2, submission=sub_b, room=room_1, start=start, end=start + hour
    )
    event.cache.clear()

    with django_assert_num_queries(5):
        v2_hydrated, v1_hydrated = build_changelog(event)
        for schedule in (v2_hydrated, v1_hydrated):
            for slot in schedule.changes["new_talks"]:
                _ = slot.submission.display_title_with_speakers
            for slot in schedule.changes["canceled_talks"]:
                _ = slot.submission.display_title_with_speakers
            for move in schedule.changes["moved_talks"]:
                _ = move["submission"].display_title_with_speakers

    assert (v1_hydrated.changes["action"], v1_hydrated.changes["count"]) == (
        "create",
        0,
    )
    changes = v2_hydrated.changes
    assert (changes["action"], changes["count"]) == ("update", 3)
    assert [slot.submission for slot in changes["new_talks"]] == [sub_b]
    assert [move["submission"] for move in changes["moved_talks"]] == [sub_a]
    assert [slot.submission for slot in changes["canceled_talks"]] == [sub_c]
