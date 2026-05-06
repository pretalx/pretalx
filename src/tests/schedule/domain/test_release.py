# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django_scopes import scope

from pretalx.mail.models import QueuedMail
from pretalx.schedule.domain.release import (
    freeze_schedule,
    guess_schedule_version,
    unfreeze_schedule,
)
from pretalx.schedule.models.slot import SlotType
from pretalx.schedule.signals import schedule_release
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    EventFactory,
    RoomFactory,
    ScheduleFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("previous_version", "expected"),
    (
        (None, "0.1"),
        ("0.1", "0.2"),
        ("0,2", "0,3"),
        ("0-3", "0-4"),
        ("0_4", "0_5"),
        ("1.0.1", "1.0.2"),
        ("something.1", "something.2"),
        ("Nichtnumerisch", ""),
        ("1.something", ""),
    ),
)
def test_guess_schedule_version(previous_version, expected):
    event = EventFactory()
    if previous_version:
        ScheduleFactory(event=event, version=previous_version)
    assert guess_schedule_version(event) == expected


def test_freeze_schedule_basic():
    submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = submission.event
    room = RoomFactory(event=event)
    wip = event.wip_schedule
    TalkSlotFactory(
        schedule=wip,
        submission=submission,
        room=room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )

    with scope(event=event):
        released, new_wip = freeze_schedule(
            wip, "v1", comment="Release notes", notify_speakers=False
        )

    assert released.version == "v1"
    assert released.comment == "Release notes"
    assert released.published is not None
    assert new_wip.version is None
    assert released.talks.count() == 1
    assert new_wip.talks.count() == 1


@pytest.mark.parametrize(
    ("name", "match"),
    (
        ("wip", "reserved name"),
        ("latest", "reserved name"),
        ("", "without a version name"),
    ),
)
def test_freeze_schedule_rejects_invalid_name(event, name, match):
    with scope(event=event), pytest.raises(ValueError, match=match):
        freeze_schedule(event.wip_schedule, name)


def test_freeze_schedule_rejects_already_frozen():
    event = EventFactory()
    wip = event.wip_schedule
    released, _ = freeze_schedule(wip, "v1", notify_speakers=False)

    with pytest.raises(ValueError, match="already versioned"):
        freeze_schedule(released, "v2")


def test_freeze_schedule_sets_visibility_for_confirmed_and_breaks():
    confirmed = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = confirmed.event
    unconfirmed = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    room = RoomFactory(event=event)
    wip = event.wip_schedule
    start = event.datetime_from
    end = start + dt.timedelta(hours=1)

    TalkSlotFactory(schedule=wip, submission=confirmed, room=room, start=start, end=end)
    TalkSlotFactory(
        schedule=wip,
        submission=unconfirmed,
        room=room,
        start=start + dt.timedelta(hours=2),
        end=end + dt.timedelta(hours=2),
    )
    TalkSlotFactory(
        submission=None,
        schedule=wip,
        room=room,
        start=start + dt.timedelta(hours=4),
        end=end + dt.timedelta(hours=4),
        is_visible=False,
        slot_type=SlotType.BREAK,
        description="Coffee Break",
    )

    with scope(event=event):
        released, _ = freeze_schedule(wip, "v1", notify_speakers=False)

    confirmed_slot = released.talks.get(submission=confirmed)
    unconfirmed_slot = released.talks.get(submission=unconfirmed)
    break_slot = released.talks.get(slot_type=SlotType.BREAK)

    assert confirmed_slot.is_visible is True
    assert unconfirmed_slot.is_visible is False
    assert break_slot.is_visible is True


def test_freeze_schedule_removes_blockers_from_released():
    event = EventFactory()
    room = RoomFactory(event=event)
    wip = event.wip_schedule
    start = event.datetime_from

    TalkSlotFactory(
        submission=None,
        schedule=wip,
        room=room,
        start=start,
        end=start + dt.timedelta(hours=1),
        slot_type=SlotType.BLOCKER,
        description="Blocked",
    )

    with scope(event=event):
        released, new_wip = freeze_schedule(wip, "v1", notify_speakers=False)

    assert released.talks.filter(slot_type=SlotType.BLOCKER).count() == 0
    assert new_wip.talks.filter(slot_type=SlotType.BLOCKER).count() == 1


def test_freeze_schedule_fires_signal(event, register_signal_handler):
    received = []

    def handler(signal, sender, **kwargs):
        received.append(kwargs)

    register_signal_handler(schedule_release, handler)

    with scope(event=event):
        released, _ = freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    assert len(received) == 1
    assert received[0]["schedule"] == released


def test_freeze_schedule_invalidates_wip_cache():
    event = EventFactory()
    old_wip = event.wip_schedule
    freeze_schedule(old_wip, "v1", notify_speakers=False)

    assert event.wip_schedule.version is None
    assert event.wip_schedule.pk != old_wip.pk


@pytest.mark.usefixtures("locmem_cache")
def test_freeze_schedule_clears_unreleased_changes_flag():
    event = EventFactory()
    event.cache.set("has_unreleased_schedule_changes", True)
    freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    assert event.cache.get("has_unreleased_schedule_changes") is False


def test_freeze_schedule_with_notify_speakers():
    submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = submission.event
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    room = RoomFactory(event=event)
    wip = event.wip_schedule
    TalkSlotFactory(
        schedule=wip,
        submission=submission,
        room=room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )

    with scope(event=event):
        released, _ = freeze_schedule(wip, "v1", notify_speakers=True)

    assert QueuedMail.objects.filter(to_users=speaker.user).count() == 1


def test_unfreeze_schedule_basic():
    submission = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = submission.event
    room = RoomFactory(event=event)
    start = event.datetime_from
    end = start + dt.timedelta(hours=1)

    TalkSlotFactory(
        schedule=event.wip_schedule,
        submission=submission,
        room=room,
        start=start,
        end=end,
    )
    released_v1, _ = freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    # Modify WIP: remove the slot
    wip = event.wip_schedule
    wip.talks.all().update(room=None, start=None, end=None)
    _, _ = freeze_schedule(wip, "v2", notify_speakers=False)

    _, new_wip = unfreeze_schedule(released_v1)

    assert new_wip.version is None
    assert new_wip.talks.filter(submission=submission).count() == 1


def test_unfreeze_schedule_rejects_wip(event):
    with scope(event=event), pytest.raises(ValueError, match="not released yet"):
        unfreeze_schedule(event.wip_schedule)


def test_unfreeze_schedule_preserves_talks_from_both_versions():
    """Unfreezing merges talks from the old version and the current WIP
    (the bug72 scenario: talks added after v1 are preserved)."""
    sub1 = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = sub1.event
    room = RoomFactory(event=event)
    start = event.datetime_from
    end = start + dt.timedelta(hours=1)

    TalkSlotFactory(
        schedule=event.wip_schedule, submission=sub1, room=room, start=start, end=end
    )
    released_v1, _ = freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    sub2 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    wip = event.wip_schedule
    TalkSlotFactory(
        schedule=wip,
        submission=sub2,
        room=room,
        start=start + dt.timedelta(hours=2),
        end=end + dt.timedelta(hours=2),
    )
    freeze_schedule(wip, "v2", notify_speakers=False)

    _, new_wip = unfreeze_schedule(released_v1)

    assert new_wip.talks.count() == 2
    submission_ids = set(new_wip.talks.values_list("submission_id", flat=True))
    assert submission_ids == {sub1.pk, sub2.pk}


@pytest.mark.usefixtures("locmem_cache")
def test_unfreeze_schedule_clears_unreleased_changes_flag():
    event = EventFactory()
    released, _ = freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
    event.cache.set("has_unreleased_schedule_changes", True)

    unfreeze_schedule(released)

    assert event.cache.get("has_unreleased_schedule_changes") is False
