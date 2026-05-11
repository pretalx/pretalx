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


def test_build_changelog_returns_empty_without_released_schedules(event):
    assert build_changelog(event) == []


def test_build_changelog_skips_wip_schedule(event):
    ScheduleFactory(event=event, version="v1")
    ScheduleFactory(event=event, version=None, published=None)

    result = build_changelog(event)

    assert [s.version for s in result] == ["v1"]


def test_build_changelog_chains_previous_schedule(event):
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


def test_build_changelog_populates_scheduled_talks(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    room = RoomFactory(event=event)
    schedule = ScheduleFactory(event=event, version="v1")
    TalkSlotFactory(
        schedule=schedule,
        submission=submission,
        room=room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )

    result = build_changelog(event)

    assert len(result) == 1
    talks = result[0].scheduled_talks
    assert len(talks) == 1
    assert talks[0].submission == submission


def test_build_changelog_filters_hidden_and_unassigned_slots(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    room = RoomFactory(event=event)
    schedule = ScheduleFactory(event=event, version="v1")
    TalkSlotFactory(
        schedule=schedule,
        submission=submission,
        room=room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
        is_visible=False,
    )
    TalkSlotFactory(
        schedule=schedule,
        submission=submission,
        room=None,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )
    TalkSlotFactory(
        schedule=schedule, submission=submission, room=room, start=None, end=None
    )

    result = build_changelog(event)

    assert result[0].scheduled_talks == []


def test_build_changelog_uses_batched_slot_query(event, django_assert_num_queries):
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    room = RoomFactory(event=event)
    for version in ("v1", "v2", "v3"):
        schedule = ScheduleFactory(event=event, version=version)
        TalkSlotFactory(
            schedule=schedule,
            submission=submission,
            room=room,
            start=event.datetime_from,
            end=event.datetime_from + dt.timedelta(hours=1),
        )

    # 1 query for schedules, 1 for slots, 1 for the speakers prefetch.
    # Independent of how many schedules exist.
    with django_assert_num_queries(3):
        result = build_changelog(event)
        for schedule in result:
            list(schedule.scheduled_talks)

    assert len(result) == 3


def _release_v1_v2_with_move_new_and_canceled(event):
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
    return v1, v2, sub_a, sub_b, sub_c


def test_build_changelog_computes_real_changes(event):
    """v1 has talks A and C; v2 moves A, adds B, and cancels C.
    Exercises `_handle_submission_move` plus the new/canceled paths."""
    v1, v2, sub_a, sub_b, sub_c = _release_v1_v2_with_move_new_and_canceled(event)

    result = build_changelog(event)
    v2_hydrated, v1_hydrated = result

    assert v1_hydrated.changes["action"] == "create"
    assert v1_hydrated.changes["count"] == 0

    changes = v2_hydrated.changes
    assert changes["action"] == "update"
    assert changes["count"] == 3
    assert {slot.submission_id for slot in changes["new_talks"]} == {sub_b.pk}
    assert {move["submission"].pk for move in changes["moved_talks"]} == {sub_a.pk}
    assert {slot.submission_id for slot in changes["canceled_talks"]} == {sub_c.pk}


def test_build_changelog_changes_access_does_not_n_plus_one(
    event, django_assert_num_queries
):
    """Accessing `.changes` on every hydrated schedule must not fire per-slot
    queries — the whole point of pre-populating previous_schedule and
    scheduled_talks. The cache-miss path runs purely off the in-memory lists."""
    _release_v1_v2_with_move_new_and_canceled(event)
    event.cache.clear()

    # 3 queries for build_changelog (schedules, slots, speakers prefetch).
    # `.changes` access on cache miss runs off the pre-populated lists; the
    # locmem cache backend used in tests adds no DB queries.
    with django_assert_num_queries(3):
        result = build_changelog(event)
        for schedule in result:
            _ = schedule.changes
            for slot in schedule.changes["new_talks"]:
                _ = slot.submission.display_title_with_speakers
            for slot in schedule.changes["canceled_talks"]:
                _ = slot.submission.display_title_with_speakers
            for move in schedule.changes["moved_talks"]:
                _ = move["submission"].display_title_with_speakers
