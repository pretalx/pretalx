import datetime as dt

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.common.context_processors import get_day_month_date_format
from pretalx.schedule.notifications import (
    get_current_notifications,
    get_full_notifications,
    get_notification_date_format,
    render_notifications,
)
from pretalx.schedule.services import freeze_schedule
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    RoomFactory,
    ScheduleFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


def test_get_notification_date_format():
    result = get_notification_date_format()
    assert "," in result
    assert result.startswith(get_day_month_date_format())


@pytest.mark.django_db
def test_render_notifications_with_created_slot(event):
    """render_notifications produces text mentioning the talk title for new slots."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        slot = TalkSlotFactory(submission=submission, is_visible=True)

    data = {"create": [slot], "update": []}

    result = render_notifications(data, event)

    assert submission.title in result


@pytest.mark.django_db
def test_render_notifications_with_moved_slot(event):
    """render_notifications renders update entries for moved talks."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        room = RoomFactory(event=event)
        slot = TalkSlotFactory(submission=submission, is_visible=True, room=room)

    moved = {
        "submission": submission,
        "old_start": slot.local_start,
        "new_start": slot.local_start + dt.timedelta(hours=2),
        "old_room": slot.room,
        "new_room": room,
        "new_info": "",
        "new_slot": slot,
    }
    data = {"create": [], "update": [moved]}

    result = render_notifications(data, event)

    assert submission.title in result
    assert "moved" in result.lower()


@pytest.mark.django_db
def test_render_notifications_empty_data(event):
    data = {"create": [], "update": []}

    result = render_notifications(data, event)

    assert result.strip() == ""


@pytest.mark.parametrize(
    "notification_fn",
    (
        pytest.param(get_full_notifications, id="get_full_notifications"),
        pytest.param(get_current_notifications, id="get_current_notifications"),
    ),
)
@pytest.mark.django_db
def test_notifications_no_current_schedule_returns_empty(notification_fn, event):
    with scopes_disabled():
        result = notification_fn(UserFactory(), event)

    assert result == {"create": [], "update": []}


@pytest.mark.parametrize(
    "notification_fn",
    (
        pytest.param(get_full_notifications, id="get_full_notifications"),
        pytest.param(get_current_notifications, id="get_current_notifications"),
    ),
)
@pytest.mark.django_db
def test_notifications_returns_speakers_slot(notification_fn, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        slot = TalkSlotFactory(submission=submission, is_visible=True)
        schedule = slot.schedule
        schedule.version = "1.0"
        schedule.published = now()
        schedule.save()
        ScheduleFactory(event=event)

    with scopes_disabled():
        result = notification_fn(speaker.user, event)

    assert list(result["create"]) == [slot]
    assert result["update"] == []


@pytest.mark.django_db
def test_get_full_notifications_excludes_other_speakers_talks(event):
    """Only talks belonging to the queried user are included."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        other_speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(other_speaker)
        TalkSlotFactory(submission=submission, is_visible=True)
        schedule = event.wip_schedule
        schedule.version = "1.0"
        schedule.published = now()
        schedule.save()
        ScheduleFactory(event=event)

    with scopes_disabled():
        result = get_full_notifications(speaker.user, event)

    assert list(result["create"]) == []


@pytest.mark.django_db
def test_get_current_notifications_returns_empty_for_unrelated_user(event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        slot = TalkSlotFactory(submission=submission, is_visible=True)
        schedule = slot.schedule
        schedule.version = "1.0"
        schedule.published = now()
        schedule.save()
        ScheduleFactory(event=event)

    with scopes_disabled():
        unrelated_user = UserFactory()
        result = get_current_notifications(unrelated_user, event)

    assert result == {"create": [], "update": []}


@pytest.mark.django_db
def test_get_current_notifications_returns_moved_talk(event):
    """When a talk is moved to a different room between releases,
    get_current_notifications returns it in the update list."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        TalkSlotFactory(submission=submission, is_visible=True)
        freeze_schedule(event.wip_schedule, "1.0", notify_speakers=False)

        # Move the talk to a different room in the WIP schedule
        wip_slot = event.wip_schedule.talks.get(submission=submission)
        new_room = RoomFactory(event=event)
        wip_slot.room = new_room
        wip_slot.save()
        freeze_schedule(event.wip_schedule, "2.0", notify_speakers=False)

    with scopes_disabled():
        result = get_current_notifications(speaker.user, event)

    assert result["create"] == []
    assert len(result["update"]) == 1
    assert result["update"][0]["submission"] == submission
    assert result["update"][0]["new_room"] == new_room


@pytest.mark.django_db
def test_get_current_notifications_empty_after_unchanged_release(event):
    """After a second release with unchanged slots, get_current_notifications
    returns empty (no changes) while get_full_notifications still returns the
    speaker's talk."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        TalkSlotFactory(submission=submission, is_visible=True)
        freeze_schedule(event.wip_schedule, "1.0", notify_speakers=False)
        freeze_schedule(event.wip_schedule, "2.0", notify_speakers=False)

    with scopes_disabled():
        current = get_current_notifications(speaker.user, event)
        full = get_full_notifications(speaker.user, event)

    assert current == {"create": [], "update": []}
    assert list(full["create"])[0].submission == submission
    assert full["update"] == []
