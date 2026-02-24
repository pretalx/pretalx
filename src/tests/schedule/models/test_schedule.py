import datetime as dt

import pytest
from django.db.utils import IntegrityError
from django.utils.timezone import now as tz_now
from django_scopes import scope, scopes_disabled

from pretalx.schedule.models import Schedule
from pretalx.schedule.models.slot import SlotType
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    AvailabilityFactory,
    EventFactory,
    RoomFactory,
    ScheduleFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    TrackFactory,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("version", "expected_suffix"),
    ((None, "version=None"), ("v1", "version=v1")),
    ids=["no_version", "with_version"],
)
@pytest.mark.django_db
def test_schedule_str(version, expected_suffix):
    schedule = ScheduleFactory(version=version)
    assert str(schedule) == f"Schedule(event={schedule.event.slug}, {expected_suffix})"


@pytest.mark.parametrize(
    ("version", "expected"),
    ((None, "wip"), ("v2", "v2")),
    ids=["none_returns_wip", "returns_version"],
)
@pytest.mark.django_db
def test_schedule_version_with_fallback(version, expected):
    schedule = ScheduleFactory(version=version)
    assert schedule.version_with_fallback == expected


@pytest.mark.parametrize(
    ("version", "expected"),
    ((None, "wip"), ("v1", "v1"), ("version 1", "version%201")),
    ids=["wip", "plain", "encoded"],
)
@pytest.mark.django_db
def test_schedule_url_version(version, expected):
    schedule = ScheduleFactory(version=version)
    assert schedule.url_version == expected


@pytest.mark.django_db
def test_schedule_is_archived_no_version(event):
    with scope(event=event):
        assert not event.wip_schedule.is_archived


@pytest.mark.django_db
def test_schedule_is_archived_current(event):
    with scope(event=event):
        event.release_schedule(name="v1")
        v1 = Schedule.objects.get(event=event, version="v1")
        assert not v1.is_archived


@pytest.mark.django_db
def test_schedule_is_archived_old(event):
    with scope(event=event):
        event.release_schedule(name="v1")
        event.release_schedule(name="v2")
        v1 = Schedule.objects.get(event=event, version="v1")
        assert v1.is_archived


@pytest.mark.django_db
def test_schedule_scheduled_talks_filters_visible(event):
    """scheduled_talks only returns visible slots with room, start, and submission."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    room = RoomFactory(event=event)
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
    TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=event.datetime_from + dt.timedelta(hours=2),
        end=event.datetime_from + dt.timedelta(hours=3),
        is_visible=False,
    )

    with scope(event=event):
        result = list(schedule.scheduled_talks)

    assert result == [slot]


@pytest.mark.django_db
def test_schedule_scheduled_talks_excludes_no_room(event):
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(
        submission=submission, schedule=schedule, room=None, is_visible=True
    )

    with scope(event=event):
        assert list(schedule.scheduled_talks) == []


@pytest.mark.django_db
def test_schedule_scheduled_talks_excludes_no_start(event):
    submission = SubmissionFactory(event=event)
    room = RoomFactory(event=event)
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
        assert list(schedule.scheduled_talks) == []


@pytest.mark.django_db
def test_schedule_breaks(event):
    room = RoomFactory(event=event)
    with scope(event=event):
        schedule = event.wip_schedule
    break_slot = TalkSlotFactory(
        submission=None,
        schedule=schedule,
        room=room,
        slot_type=SlotType.BREAK,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )
    TalkSlotFactory(
        submission=SubmissionFactory(event=event), schedule=schedule, room=room
    )

    with scope(event=event):
        result = list(schedule.breaks)

    assert result == [break_slot]


@pytest.mark.django_db
def test_schedule_blockers(event):
    room = RoomFactory(event=event)
    with scope(event=event):
        schedule = event.wip_schedule
    blocker = TalkSlotFactory(
        submission=None,
        schedule=schedule,
        room=room,
        slot_type=SlotType.BLOCKER,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )
    TalkSlotFactory(
        submission=SubmissionFactory(event=event), schedule=schedule, room=room
    )

    with scope(event=event):
        result = list(schedule.blockers)

    assert result == [blocker]


@pytest.mark.django_db
def test_schedule_slots_returns_submissions(event):
    """The slots property returns Submission objects, not TalkSlot objects."""
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    room = RoomFactory(event=event)
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

    with scopes_disabled():
        result = list(schedule.slots)

    assert result == [submission]


@pytest.mark.django_db
def test_schedule_previous_schedule_none(event):
    with scope(event=event):
        schedule = event.wip_schedule
        assert schedule.previous_schedule is None


@pytest.mark.django_db
def test_schedule_previous_schedule_returns_last_published(event):
    with scope(event=event):
        event.release_schedule(name="v1")
        event.release_schedule(name="v2")
        v2 = Schedule.objects.get(event=event, version="v2")
        v1 = Schedule.objects.get(event=event, version="v1")
        assert v2.previous_schedule == v1


@pytest.mark.django_db
def test_schedule_previous_schedule_wip_returns_latest_published(event):
    with scope(event=event):
        event.release_schedule(name="v1")
        wip = event.wip_schedule
        v1 = Schedule.objects.get(event=event, version="v1")
        assert wip.previous_schedule == v1


@pytest.mark.django_db
def test_schedule_use_room_availabilities_false(event):
    with scope(event=event):
        assert event.wip_schedule.use_room_availabilities is False


@pytest.mark.django_db
def test_schedule_use_room_availabilities_true(event):
    room = RoomFactory(event=event)
    AvailabilityFactory(event=event, room=room)
    with scope(event=event):
        assert event.wip_schedule.use_room_availabilities is True


@pytest.mark.django_db
def test_schedule_get_talk_warnings_empty_for_unscheduled(event):
    """No warnings for a slot without start, submission, or room."""
    with scope(event=event):
        schedule = event.wip_schedule
    slot = TalkSlotFactory(
        submission=None, schedule=schedule, room=None, start=None, end=None
    )

    assert schedule.get_talk_warnings(slot) == []


@pytest.mark.django_db
def test_schedule_get_talk_warnings_room_overlap(event):
    """Overlapping slots in the same room produce a room_overlap warning."""
    room = RoomFactory(event=event)
    submission1 = SubmissionFactory(event=event)
    submission2 = SubmissionFactory(event=event)
    start = event.datetime_from
    end = start + dt.timedelta(hours=1)
    with scope(event=event):
        schedule = event.wip_schedule
    slot1 = TalkSlotFactory(
        submission=submission1, schedule=schedule, room=room, start=start, end=end
    )
    TalkSlotFactory(
        submission=submission2, schedule=schedule, room=room, start=start, end=end
    )

    with scope(event=event):
        warnings = schedule.get_talk_warnings(slot1, with_speakers=False)

    assert len(warnings) == 1
    assert warnings[0]["type"] == "room_overlap"


@pytest.mark.django_db
def test_schedule_get_talk_warnings_room_availability(event):
    """A slot in a room outside the room's availability raises a room warning."""
    room = RoomFactory(event=event)
    AvailabilityFactory(
        event=event,
        room=room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=2),
    )
    submission = SubmissionFactory(event=event)
    late_start = event.datetime_from + dt.timedelta(hours=10)
    with scope(event=event):
        schedule = event.wip_schedule
    slot = TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=late_start,
        end=late_start + dt.timedelta(hours=1),
    )

    with scope(event=event):
        warnings = schedule.get_talk_warnings(slot, with_speakers=False)

    assert len(warnings) == 1
    assert warnings[0]["type"] == "room"


@pytest.mark.django_db
def test_schedule_get_talk_warnings_speaker_overlap(event):
    """A speaker scheduled for two overlapping slots produces a speaker warning."""
    room1 = RoomFactory(event=event)
    room2 = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission1 = SubmissionFactory(event=event)
    submission2 = SubmissionFactory(event=event)
    with scopes_disabled():
        submission1.speakers.add(speaker)
        submission2.speakers.add(speaker)
    start = event.datetime_from
    end = start + dt.timedelta(hours=1)
    with scope(event=event):
        schedule = event.wip_schedule
    slot1 = TalkSlotFactory(
        submission=submission1, schedule=schedule, room=room1, start=start, end=end
    )
    TalkSlotFactory(
        submission=submission2, schedule=schedule, room=room2, start=start, end=end
    )

    with scope(event=event):
        warnings = schedule.get_talk_warnings(slot1, with_speakers=True)

    speaker_warnings = [w for w in warnings if w["type"] == "speaker"]
    assert len(speaker_warnings) == 1
    assert speaker_warnings[0]["speaker"]["code"] == speaker.code


@pytest.mark.django_db
def test_schedule_get_talk_warnings_speaker_availability(event):
    """A speaker unavailable at the slot time produces a speaker warning."""
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    AvailabilityFactory(
        event=event,
        person=speaker,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)
    late_start = event.datetime_from + dt.timedelta(hours=10)
    with scope(event=event):
        schedule = event.wip_schedule
    slot = TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=late_start,
        end=late_start + dt.timedelta(hours=1),
    )

    with scope(event=event):
        warnings = schedule.get_talk_warnings(slot, with_speakers=True)

    speaker_warnings = [w for w in warnings if w["type"] == "speaker"]
    assert len(speaker_warnings) == 1
    assert speaker_warnings[0]["speaker"]["code"] == speaker.code


@pytest.mark.django_db
def test_schedule_get_talk_warnings_no_speaker_avail_when_disabled(event):
    """with_speakers=False skips speaker availability checks."""
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    AvailabilityFactory(
        event=event,
        person=speaker,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )
    submission = SubmissionFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)
    late_start = event.datetime_from + dt.timedelta(hours=10)
    with scope(event=event):
        schedule = event.wip_schedule
    slot = TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=late_start,
        end=late_start + dt.timedelta(hours=1),
    )

    with scope(event=event):
        warnings = schedule.get_talk_warnings(slot, with_speakers=False)

    speaker_avail_warnings = [
        w
        for w in warnings
        if w["type"] == "speaker" and "not available" in w["message"]
    ]
    assert speaker_avail_warnings == []


@pytest.mark.django_db
def test_schedule_get_all_talk_warnings(event):
    room = RoomFactory(event=event)
    submission1 = SubmissionFactory(event=event)
    submission2 = SubmissionFactory(event=event)
    start = event.datetime_from
    end = start + dt.timedelta(hours=1)
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(
        submission=submission1, schedule=schedule, room=room, start=start, end=end
    )
    TalkSlotFactory(
        submission=submission2, schedule=schedule, room=room, start=start, end=end
    )

    with scope(event=event):
        result = schedule.get_all_talk_warnings()

    assert len(result) == 2
    for warnings in result.values():
        assert any(w["type"] == "room_overlap" for w in warnings)


@pytest.mark.django_db
def test_schedule_get_all_talk_warnings_filter_updated(event):
    """filter_updated excludes talks not updated since the given time."""
    room = RoomFactory(event=event)
    submission = SubmissionFactory(event=event)
    start = event.datetime_from
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=start,
        end=start + dt.timedelta(hours=1),
    )

    future = tz_now() + dt.timedelta(hours=1)
    with scope(event=event):
        result = schedule.get_all_talk_warnings(filter_updated=future)

    assert result == {}


@pytest.mark.django_db
def test_schedule_warnings_unscheduled_count(event):
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(
        submission=submission, schedule=schedule, room=None, start=None, end=None
    )

    with scope(event=event):
        result = schedule.warnings

    assert result["unscheduled"] == 1


@pytest.mark.django_db
def test_schedule_warnings_unconfirmed_count(event):
    submission = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    room = RoomFactory(event=event)
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
        result = schedule.warnings

    assert result["unconfirmed"] == 1


@pytest.mark.django_db
def test_schedule_warnings_no_track_when_tracks_enabled(event):
    event.feature_flags = {**event.feature_flags, "use_tracks": True}
    event.save()
    TrackFactory(event=event)
    submission = SubmissionFactory(event=event, track=None)
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(submission=submission, schedule=schedule)

    with scope(event=event):
        result = schedule.warnings

    assert result["no_track"].count() == 1


@pytest.mark.django_db
def test_schedule_warnings_no_track_empty_when_tracks_disabled(event):
    event.feature_flags = {**event.feature_flags, "use_tracks": False}
    event.save()
    submission = SubmissionFactory(event=event, track=None)
    with scope(event=event):
        schedule = event.wip_schedule
    TalkSlotFactory(submission=submission, schedule=schedule)

    with scope(event=event):
        result = schedule.warnings

    assert result["no_track"] == []


@pytest.mark.django_db
def test_schedule_changes_create_on_first_release(event):
    """First release has action 'create'."""
    with scope(event=event):
        event.release_schedule(name="v1")
        v1 = Schedule.objects.get(event=event, version="v1")

    with scope(event=event):
        assert v1.changes["action"] == "create"


@pytest.mark.django_db
def test_schedule_changes_update_with_new_talk(event):
    """Adding a new talk between releases shows it in new_talks."""
    room = RoomFactory(event=event)
    with scope(event=event):
        event.release_schedule(name="v1")
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        event.wip_schedule.talks.create(
            submission=submission,
            room=room,
            start=event.datetime_from,
            end=event.datetime_from + dt.timedelta(hours=1),
            is_visible=True,
        )
        event.release_schedule(name="v2")
        v2 = Schedule.objects.get(event=event, version="v2")

        assert v2.changes["action"] == "update"
        assert len(v2.changes["new_talks"]) == 1
        assert v2.changes["new_talks"][0].submission == submission


@pytest.mark.django_db
def test_schedule_changes_canceled_talk(event):
    """Removing a scheduled talk between releases shows it in canceled_talks."""
    room = RoomFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scope(event=event):
        event.wip_schedule.talks.create(
            submission=submission,
            room=room,
            start=event.datetime_from,
            end=event.datetime_from + dt.timedelta(hours=1),
            is_visible=True,
        )
        event.release_schedule(name="v1")
        wip_slot = event.wip_schedule.talks.get(submission=submission)
        wip_slot.room = None
        wip_slot.start = None
        wip_slot.end = None
        wip_slot.is_visible = False
        wip_slot.save()
        event.release_schedule(name="v2")
        v2 = Schedule.objects.get(event=event, version="v2")

        assert v2.changes["action"] == "update"
        assert len(v2.changes["canceled_talks"]) == 1


@pytest.mark.django_db
def test_schedule_changes_moved_talk(event):
    """Moving a talk to a different time between releases shows it in moved_talks."""
    room = RoomFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scope(event=event):
        event.wip_schedule.talks.create(
            submission=submission,
            room=room,
            start=event.datetime_from,
            end=event.datetime_from + dt.timedelta(hours=1),
            is_visible=True,
        )
        event.release_schedule(name="v1")
        wip_slot = event.wip_schedule.talks.get(submission=submission)
        wip_slot.start = event.datetime_from + dt.timedelta(hours=5)
        wip_slot.end = event.datetime_from + dt.timedelta(hours=6)
        wip_slot.save()
        event.release_schedule(name="v2")
        v2 = Schedule.objects.get(event=event, version="v2")

        assert v2.changes["action"] == "update"
        assert len(v2.changes["moved_talks"]) == 1
        assert v2.changes["moved_talks"][0]["submission"] == submission


@pytest.mark.django_db
def test_schedule_speakers_concerned_create(event):
    """On first release, speakers_concerned lists speakers with their new talks."""
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scopes_disabled():
        submission.speakers.add(speaker)
    with scope(event=event):
        event.wip_schedule.talks.create(
            submission=submission,
            room=room,
            start=event.datetime_from,
            end=event.datetime_from + dt.timedelta(hours=1),
            is_visible=True,
        )
        event.release_schedule(name="v1")
        v1 = Schedule.objects.get(event=event, version="v1")

        assert len(v1.speakers_concerned) == 1
        assert speaker in v1.speakers_concerned
        assert v1.speakers_concerned[speaker]["create"].count() == 1


@pytest.mark.django_db
def test_schedule_speakers_concerned_update(event):
    """On subsequent releases, speakers with moved talks appear in update."""
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scopes_disabled():
        submission.speakers.add(speaker)
    with scope(event=event):
        event.wip_schedule.talks.create(
            submission=submission,
            room=room,
            start=event.datetime_from,
            end=event.datetime_from + dt.timedelta(hours=1),
            is_visible=True,
        )
        event.release_schedule(name="v1")
        wip_slot = event.wip_schedule.talks.get(submission=submission)
        wip_slot.start = event.datetime_from + dt.timedelta(hours=5)
        wip_slot.end = event.datetime_from + dt.timedelta(hours=6)
        wip_slot.save()
        event.release_schedule(name="v2")
        v2 = Schedule.objects.get(event=event, version="v2")

        matched_speaker = [s for s in v2.speakers_concerned if s.user == speaker.user]
        assert len(matched_speaker) == 1
        assert len(v2.speakers_concerned[matched_speaker[0]]["update"]) == 1


@pytest.mark.django_db
def test_schedule_speakers_concerned_empty_when_only_cancellations(event):
    """When the only changes are cancellations, speakers_concerned is empty."""
    room = RoomFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    speaker = SpeakerFactory(event=event)
    with scopes_disabled():
        submission.speakers.add(speaker)
    with scope(event=event):
        event.wip_schedule.talks.create(
            submission=submission,
            room=room,
            start=event.datetime_from,
            end=event.datetime_from + dt.timedelta(hours=1),
            is_visible=True,
        )
        event.release_schedule(name="v1")
        wip_slot = event.wip_schedule.talks.get(submission=submission)
        wip_slot.room = None
        wip_slot.start = None
        wip_slot.end = None
        wip_slot.is_visible = False
        wip_slot.save()
        event.release_schedule(name="v2")
        v2 = Schedule.objects.get(event=event, version="v2")

        assert v2.speakers_concerned == {}


@pytest.mark.django_db
def test_schedule_speakers_concerned_create_excludes_unscheduled(event):
    """On first release, speakers with unscheduled slots are not in speakers_concerned."""
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scopes_disabled():
        submission.speakers.add(speaker)
    with scope(event=event):
        event.wip_schedule.talks.create(
            submission=submission, room=None, start=None, is_visible=True
        )
        event.release_schedule(name="v1")
        v1 = Schedule.objects.get(event=event, version="v1")

        assert speaker not in v1.speakers_concerned


@pytest.mark.django_db
def test_schedule_speakers_concerned_new_talk_in_update(event):
    """speakers_concerned includes speakers for new talks added in an update release."""
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scopes_disabled():
        submission.speakers.add(speaker)
    with scope(event=event):
        event.release_schedule(name="v1")
        event.wip_schedule.talks.create(
            submission=submission,
            room=room,
            start=event.datetime_from,
            end=event.datetime_from + dt.timedelta(hours=1),
            is_visible=True,
        )
        event.release_schedule(name="v2")
        v2 = Schedule.objects.get(event=event, version="v2")

        matched_speaker = [s for s in v2.speakers_concerned if s.user == speaker.user]
        assert len(matched_speaker) == 1
        assert len(v2.speakers_concerned[matched_speaker[0]]["create"]) == 1


@pytest.mark.django_db
def test_schedule_get_talk_warnings_room_avail_contains(event):
    """No room warning when the slot falls within provided room_avails."""
    room = RoomFactory(event=event)
    avail = AvailabilityFactory(
        event=event, room=room, start=event.datetime_from, end=event.datetime_to
    )
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        schedule = event.wip_schedule
    slot = TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=1),
    )

    with scope(event=event):
        warnings = schedule.get_talk_warnings(
            slot, with_speakers=False, room_avails=[avail]
        )

    room_warnings = [w for w in warnings if w["type"] == "room"]
    assert room_warnings == []


@pytest.mark.django_db
def test_schedule_get_talk_warnings_room_avails_none(event):
    """When room_avails is not passed, it fetches them from the room."""
    room = RoomFactory(event=event)
    AvailabilityFactory(
        event=event,
        room=room,
        start=event.datetime_from,
        end=event.datetime_from + dt.timedelta(hours=2),
    )
    submission = SubmissionFactory(event=event)
    late_start = event.datetime_from + dt.timedelta(hours=10)
    with scope(event=event):
        schedule = event.wip_schedule
    slot = TalkSlotFactory(
        submission=submission,
        schedule=schedule,
        room=room,
        start=late_start,
        end=late_start + dt.timedelta(hours=1),
    )

    with scope(event=event):
        warnings = schedule.get_talk_warnings(
            slot, with_speakers=False, room_avails=None
        )

    assert len(warnings) == 1
    assert warnings[0]["type"] == "room"


@pytest.mark.django_db
def test_schedule_generate_notifications(event):
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scopes_disabled():
        submission.speakers.add(speaker)
    with scope(event=event):
        event.wip_schedule.talks.create(
            submission=submission,
            room=room,
            start=event.datetime_from,
            end=event.datetime_from + dt.timedelta(hours=1),
            is_visible=True,
        )
        event.release_schedule(name="v1")
        v1 = Schedule.objects.get(event=event, version="v1")

    with scope(event=event):
        mails = v1.generate_notifications(save=False)

    assert len(mails) == 1


@pytest.mark.django_db
def test_schedule_generate_notifications_no_speakers(event):
    with scope(event=event):
        event.release_schedule(name="v1")
        v1 = Schedule.objects.get(event=event, version="v1")
        mails = v1.generate_notifications(save=False)

    assert mails == []


@pytest.mark.django_db
def test_schedule_freeze_returns_old_and_new(event):
    """freeze() returns the frozen schedule and a new WIP schedule."""
    room = RoomFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scope(event=event):
        event.wip_schedule.talks.create(
            submission=submission,
            room=room,
            start=event.datetime_from,
            end=event.datetime_from + dt.timedelta(hours=1),
            is_visible=True,
        )
        old, new = event.wip_schedule.freeze("v1", notify_speakers=False)

    assert old.version == "v1"
    assert old.published is not None
    assert new.version is None


@pytest.mark.parametrize("version", ("wip", "latest", ""))
@pytest.mark.django_db
def test_schedule_freeze_rejects_reserved_names(event, version):
    with (
        scope(event=event),
        pytest.raises(ValueError, match="reserved name|without a version"),
    ):
        event.wip_schedule.freeze(version, notify_speakers=False)


@pytest.mark.django_db
def test_schedule_freeze_rejects_already_versioned(event):
    with scope(event=event):
        old, _ = event.wip_schedule.freeze("v1", notify_speakers=False)
        with pytest.raises(ValueError, match="already versioned"):
            old.freeze("v2", notify_speakers=False)


@pytest.mark.django_db
def test_schedule_freeze_rejects_duplicate_version(event):
    with scope(event=event):
        event.wip_schedule.freeze("v1", notify_speakers=False)
        with pytest.raises(IntegrityError):
            event.wip_schedule.freeze("v1", notify_speakers=False)


@pytest.mark.django_db
def test_schedule_freeze_copies_talks(event):
    """freeze() copies all talks to the new WIP schedule."""
    room = RoomFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scope(event=event):
        event.wip_schedule.talks.create(
            submission=submission,
            room=room,
            start=event.datetime_from,
            end=event.datetime_from + dt.timedelta(hours=1),
            is_visible=True,
        )
        old, new = event.wip_schedule.freeze("v1", notify_speakers=False)

        assert old.talks.count() == 1
        assert new.talks.count() == 1
        assert new.talks.first().submission == submission


@pytest.mark.django_db
def test_schedule_freeze_removes_blockers_from_released(event):
    """Blockers are removed from the released schedule but kept in new WIP."""
    room = RoomFactory(event=event)
    with scope(event=event):
        event.wip_schedule.talks.create(
            room=room,
            slot_type=SlotType.BLOCKER,
            start=event.datetime_from,
            end=event.datetime_from + dt.timedelta(hours=1),
        )
        old, new = event.wip_schedule.freeze("v1", notify_speakers=False)

        assert old.blockers.count() == 0
        assert new.blockers.count() == 1


@pytest.mark.django_db
def test_schedule_freeze_invalidates_wip_cache(event):
    with scope(event=event):
        event.wip_schedule.freeze("v1", notify_speakers=False)
        assert event.wip_schedule.version is None


@pytest.mark.django_db
def test_schedule_unfreeze_restores_talks(event):
    room = RoomFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scope(event=event):
        event.wip_schedule.talks.create(
            submission=submission,
            room=room,
            start=event.datetime_from,
            end=event.datetime_from + dt.timedelta(hours=1),
            is_visible=True,
        )
        old, _ = event.wip_schedule.freeze("v1", notify_speakers=False)
        old.unfreeze()
        assert event.wip_schedule.talks.count() == 1


@pytest.mark.django_db
def test_schedule_unfreeze_unreleased_raises(event):
    with scope(event=event), pytest.raises(ValueError, match="not released yet"):
        event.wip_schedule.unfreeze()


@pytest.mark.django_db
def test_schedule_build_data_basic(event):
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
        data = schedule.build_data()

    assert data["version"] is None
    assert data["schedule_id"] == schedule.pk
    assert data["event_start"] == event.date_from.isoformat()
    assert data["event_end"] == event.date_to.isoformat()
    assert len(data["talks"]) == 1
    assert data["talks"][0]["code"] == submission.code
    assert len(data["rooms"]) == 1
    assert data["rooms"][0]["id"] == room.id


@pytest.mark.django_db
def test_schedule_build_data_excludes_invisible_by_default(event):
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
        data = schedule.build_data()

    assert len(data["talks"]) == 0


@pytest.mark.django_db
def test_schedule_build_data_all_talks_includes_invisible(event):
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
        data = schedule.build_data(all_talks=True)

    assert len(data["talks"]) == 1
    assert data["talks"][0]["state"] == submission.state


@pytest.mark.parametrize(
    ("include_blockers", "expected_count"),
    ((False, 0), (True, 1)),
    ids=["excluded_by_default", "included_when_requested"],
)
@pytest.mark.django_db
def test_schedule_build_data_blockers(event, include_blockers, expected_count):
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
        data = schedule.build_data(include_blockers=include_blockers)

    assert len(data["talks"]) == expected_count


@pytest.mark.django_db
def test_schedule_build_data_break_slot(event):
    """Break slots (no submission) are included with their slot_type."""
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
        data = schedule.build_data()

    assert len(data["talks"]) == 1
    assert data["talks"][0]["slot_type"] == SlotType.BREAK
    assert "code" not in data["talks"][0]


@pytest.mark.django_db
def test_schedule_build_data_includes_tracks(event):
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
        data = schedule.build_data()

    assert len(data["tracks"]) == 1
    assert data["tracks"][0]["id"] == track.id
    assert data["tracks"][0]["color"] == track.color


@pytest.mark.django_db
def test_schedule_build_data_includes_speakers(event):
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    with scopes_disabled():
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
        data = schedule.build_data()

    assert len(data["speakers"]) == 1
    assert data["speakers"][0]["code"] == speaker.code


@pytest.mark.django_db
def test_schedule_build_data_all_rooms(event):
    """all_rooms=True includes rooms even without scheduled talks."""
    room1 = RoomFactory(event=event)
    room2 = RoomFactory(event=event)
    with scope(event=event):
        schedule = event.wip_schedule
        data = schedule.build_data(all_rooms=True)

    room_ids = {r["id"] for r in data["rooms"]}
    assert room1.id in room_ids
    assert room2.id in room_ids


@pytest.mark.django_db
def test_schedule_build_data_filter_updated(event):
    """filter_updated limits talks to those updated after the given time."""
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
        data = schedule.build_data(filter_updated=future)

    assert len(data["talks"]) == 0


@pytest.mark.django_db
def test_schedule_unique_event_version():
    event = EventFactory()
    ScheduleFactory(event=event, version="v1")
    with pytest.raises(IntegrityError):
        ScheduleFactory(event=event, version="v1")
