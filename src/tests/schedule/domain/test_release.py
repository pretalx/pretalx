# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django_scopes import scope

from pretalx.mail.models import QueuedMail
from pretalx.schedule.domain.release import (
    apply_signup_capacity_changes,
    apply_signup_capacity_defaults,
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


def test_freeze_schedule_releases_visible_copy_and_keeps_blockers_in_wip(
    register_signal_handler,
):
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
    TalkSlotFactory(
        submission=None,
        schedule=wip,
        room=room,
        start=start + dt.timedelta(hours=6),
        end=end + dt.timedelta(hours=6),
        slot_type=SlotType.BLOCKER,
        description="Blocked",
    )
    event.cache.set("has_unreleased_schedule_changes", True)
    received = []

    def handler(signal, sender, **kwargs):
        received.append(kwargs["schedule"])

    register_signal_handler(schedule_release, handler)

    with scope(event=event):
        released, new_wip = freeze_schedule(
            wip, "v1", comment="Release notes", notify_speakers=False
        )

    assert released.version == "v1"
    assert released.comment == "Release notes"
    assert released.published is not None
    assert received == [released]
    assert new_wip.version is None
    assert new_wip.pk != wip.pk
    assert event.wip_schedule.pk == new_wip.pk
    assert event.cache.get("has_unreleased_schedule_changes") is False
    assert released.talks.get(submission=confirmed).is_visible is True
    assert released.talks.get(submission=unconfirmed).is_visible is False
    assert released.talks.get(slot_type=SlotType.BREAK).is_visible is True
    assert released.talks.filter(slot_type=SlotType.BLOCKER).count() == 0
    assert released.talks.count() == 3
    assert new_wip.talks.filter(slot_type=SlotType.BLOCKER).count() == 1
    assert new_wip.talks.count() == 4


@pytest.mark.parametrize(
    ("name", "exception", "match"),
    (
        ("wip", ValueError, "reserved name"),
        ("latest", ValueError, "reserved name"),
        ("", ValueError, "without a version name"),
        ("200 km/h", ValidationError, None),
    ),
    ids=["wip", "latest", "empty", "slash"],
)
def test_freeze_schedule_rejects_invalid_name(event, name, exception, match):
    with scope(event=event), pytest.raises(exception, match=match):
        freeze_schedule(event.wip_schedule, name)

    with scope(event=event):
        assert event.wip_schedule.version is None


def test_freeze_schedule_rejects_frozen_schedule_and_duplicate_version(event):
    with scope(event=event):
        released, _ = freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

        with pytest.raises(ValueError, match="already versioned"):
            freeze_schedule(released, "v2")
        with pytest.raises(IntegrityError):
            freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)


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

    assert QueuedMail.objects.filter(to_speakers=speaker).count() == 1


def test_unfreeze_schedule_restores_old_slots_and_keeps_newer_talks():
    sub1 = SubmissionFactory(state=SubmissionStates.CONFIRMED)
    event = sub1.event
    room = RoomFactory(event=event)
    start = event.datetime_from
    end = start + dt.timedelta(hours=1)
    TalkSlotFactory(
        schedule=event.wip_schedule, submission=sub1, room=room, start=start, end=end
    )
    with scope(event=event), pytest.raises(ValueError, match="not released yet"):
        unfreeze_schedule(event.wip_schedule)
    released_v1, _ = freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    wip = event.wip_schedule
    wip.talks.update(room=None, start=None, end=None)
    sub2 = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    TalkSlotFactory(
        schedule=wip,
        submission=sub2,
        room=room,
        start=start + dt.timedelta(hours=2),
        end=end + dt.timedelta(hours=2),
    )
    freeze_schedule(wip, "v2", notify_speakers=False)
    event.cache.set("has_unreleased_schedule_changes", True)

    _, new_wip = unfreeze_schedule(released_v1)

    assert new_wip.version is None
    assert new_wip.talks.count() == 2
    restored = new_wip.talks.get(submission=sub1)
    assert (restored.room_id, restored.start, restored.end) == (room.pk, start, end)
    assert new_wip.talks.filter(submission=sub2).count() == 1
    assert event.cache.get("has_unreleased_schedule_changes") is False


@pytest.fixture
def signup_event():
    event = EventFactory()
    event.feature_flags["attendee_signup"] = True
    event.save()
    return event


def _make_signup_slot(
    event,
    *,
    room_capacity,
    session_capacity=None,
    signup_required=True,
    is_visible=True,
):
    sub_type = event.cfp.default_type
    sub_type.attendee_signup_required = signup_required
    sub_type.save()
    room = RoomFactory(event=event, capacity=room_capacity)
    submission = SubmissionFactory(
        event=event,
        state=SubmissionStates.CONFIRMED,
        submission_type=sub_type,
        attendee_signup_capacity=session_capacity,
    )
    start = event.datetime_from
    slot = TalkSlotFactory(
        schedule=event.wip_schedule,
        submission=submission,
        room=room,
        start=start,
        end=start + dt.timedelta(hours=1),
        is_visible=is_visible,
    )
    return submission, slot


@pytest.mark.parametrize(
    (
        "feature_on",
        "room_capacity",
        "session_capacity",
        "signup_required",
        "is_visible",
        "expected",
    ),
    (
        (False, 80, None, True, True, None),  # feature off: no-op
        (True, 120, None, True, True, 120),  # default from room capacity
        (True, 120, None, True, False, 120),  # invisible scheduled slots count too
        (True, 120, 80, True, True, 80),  # keep explicit capacity
        (True, 120, None, False, True, None),  # signup not required for type
        (True, None, None, True, True, None),  # room capacity unset
    ),
)
def test_apply_signup_capacity_defaults(
    feature_on, room_capacity, session_capacity, signup_required, is_visible, expected
):
    event = EventFactory(feature_flags={"attendee_signup": feature_on})
    submission, _ = _make_signup_slot(
        event,
        room_capacity=room_capacity,
        session_capacity=session_capacity,
        signup_required=signup_required,
        is_visible=is_visible,
    )

    with scope(event=event):
        apply_signup_capacity_defaults(event.wip_schedule)

    submission.refresh_from_db()
    assert submission.attendee_signup_capacity == expected


def test_apply_signup_capacity_defaults_picks_smallest_room(signup_event):
    sub_type = signup_event.cfp.default_type
    sub_type.attendee_signup_required = True
    sub_type.save()
    big = RoomFactory(event=signup_event, capacity=200)
    small = RoomFactory(event=signup_event, capacity=50)
    submission = SubmissionFactory(
        event=signup_event, state=SubmissionStates.CONFIRMED, submission_type=sub_type
    )
    start = signup_event.datetime_from
    TalkSlotFactory(
        schedule=signup_event.wip_schedule,
        submission=submission,
        room=big,
        start=start,
        end=start + dt.timedelta(hours=1),
        is_visible=True,
    )
    TalkSlotFactory(
        schedule=signup_event.wip_schedule,
        submission=submission,
        room=small,
        start=start + dt.timedelta(hours=2),
        end=start + dt.timedelta(hours=3),
        is_visible=True,
    )

    with scope(event=signup_event):
        apply_signup_capacity_defaults(signup_event.wip_schedule)

    submission.refresh_from_db()
    assert submission.attendee_signup_capacity == 50


def test_freeze_schedule_locks_in_room_capacity(signup_event):
    submission, _ = _make_signup_slot(signup_event, room_capacity=75)

    with scope(event=signup_event):
        freeze_schedule(signup_event.wip_schedule, "v1", notify_speakers=False)

    submission.refresh_from_db()
    assert submission.attendee_signup_capacity == 75


def test_apply_signup_capacity_changes_skips_unchanged(signup_event):
    submission, _ = _make_signup_slot(
        signup_event, room_capacity=120, session_capacity=80
    )
    log_count_before = signup_event.log_entries.count()

    with scope(event=signup_event):
        apply_signup_capacity_changes(signup_event, [(submission, 80)])

    submission.refresh_from_db()
    assert submission.attendee_signup_capacity == 80
    assert signup_event.log_entries.count() == log_count_before
