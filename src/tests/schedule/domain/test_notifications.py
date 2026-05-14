# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django_scopes import scope
from i18nfield.strings import LazyI18nString

from pretalx.common.language import get_day_month_date_format
from pretalx.schedule.domain.notifications import (
    count_pending_notifications,
    generate_notifications,
    get_current_notifications,
    get_full_notifications,
    get_notification_date_format,
    render_notifications,
)
from pretalx.schedule.domain.release import freeze_schedule
from pretalx.schedule.models import Schedule
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    RoomFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_get_notification_date_format():
    result = get_notification_date_format()
    assert "," in result
    assert result.startswith(get_day_month_date_format())


def test_render_notifications_with_created_slot(event):
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    slot = TalkSlotFactory(submission=submission, is_visible=True)

    data = {"create": [slot], "update": []}

    result = render_notifications(data, event)

    assert submission.title in result


def test_render_notifications_with_moved_slot(event):
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
def test_notifications_no_current_schedule_returns_empty(notification_fn, event):
    result = notification_fn(UserFactory(), event)

    assert result == {"create": [], "update": []}


@pytest.mark.parametrize(
    "notification_fn",
    (
        pytest.param(get_full_notifications, id="get_full_notifications"),
        pytest.param(get_current_notifications, id="get_current_notifications"),
    ),
)
def test_notifications_returns_speakers_slot(notification_fn, event):
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    slot = TalkSlotFactory(submission=submission, is_visible=True)
    freeze_schedule(slot.schedule, "1.0", notify_speakers=False)

    result = notification_fn(speaker.user, event)

    assert list(result["create"]) == [slot]
    assert result["update"] == []


def test_get_full_notifications_excludes_other_speakers_talks(event):
    speaker = SpeakerFactory(event=event)
    other_speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(other_speaker)
    TalkSlotFactory(submission=submission, is_visible=True)
    freeze_schedule(event.wip_schedule, "1.0", notify_speakers=False)

    result = get_full_notifications(speaker.user, event)

    assert list(result["create"]) == []


def test_get_current_notifications_returns_empty_for_unrelated_user(event):
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    slot = TalkSlotFactory(submission=submission, is_visible=True)
    freeze_schedule(slot.schedule, "1.0", notify_speakers=False)

    unrelated_user = UserFactory()
    result = get_current_notifications(unrelated_user, event)

    assert result == {"create": [], "update": []}


def test_get_current_notifications_returns_moved_talk(event):
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

    result = get_current_notifications(speaker.user, event)

    assert result["create"] == []
    assert len(result["update"]) == 1
    assert result["update"][0]["submission"] == submission
    assert result["update"][0]["new_room"] == new_room


def test_get_current_notifications_empty_after_unchanged_release(event):
    """After a second release with unchanged slots, get_current_notifications
    returns empty (no changes) while get_full_notifications still returns the
    speaker's talk."""
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    TalkSlotFactory(submission=submission, is_visible=True)
    freeze_schedule(event.wip_schedule, "1.0", notify_speakers=False)
    freeze_schedule(event.wip_schedule, "2.0", notify_speakers=False)

    current = get_current_notifications(speaker.user, event)
    full = get_full_notifications(speaker.user, event)

    assert current == {"create": [], "update": []}
    assert list(full["create"])[0].submission == submission
    assert full["update"] == []


def test_schedule_speakers_concerned_create(event):
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    TalkSlotFactory(submission=submission, room=room)
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        v1 = Schedule.objects.get(event=event, version="v1")

        assert len(v1.speakers_concerned) == 1
        assert speaker in v1.speakers_concerned
        assert v1.speakers_concerned[speaker]["create"].count() == 1


def test_schedule_speakers_concerned_update(event):
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    TalkSlotFactory(submission=submission, room=room)
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        wip_slot = event.wip_schedule.talks.get(submission=submission)
        wip_slot.start = event.datetime_from + dt.timedelta(hours=5)
        wip_slot.end = event.datetime_from + dt.timedelta(hours=6)
        wip_slot.save()
        freeze_schedule(event.wip_schedule, "v2", notify_speakers=False)
        v2 = Schedule.objects.get(event=event, version="v2")

        matched_speaker = [s for s in v2.speakers_concerned if s.user == speaker.user]
        assert len(matched_speaker) == 1
        assert len(v2.speakers_concerned[matched_speaker[0]]["update"]) == 1


def test_schedule_speakers_concerned_empty_when_only_cancellations(event):
    room = RoomFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    speaker = SpeakerFactory(event=event)
    submission.speakers.add(speaker)
    TalkSlotFactory(submission=submission, room=room)
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        wip_slot = event.wip_schedule.talks.get(submission=submission)
        wip_slot.room = None
        wip_slot.start = None
        wip_slot.end = None
        wip_slot.is_visible = False
        wip_slot.save()
        freeze_schedule(event.wip_schedule, "v2", notify_speakers=False)
        v2 = Schedule.objects.get(event=event, version="v2")

        assert v2.speakers_concerned == {}


def test_schedule_speakers_concerned_create_excludes_unscheduled(event):
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    TalkSlotFactory(submission=submission, room=None, start=None, end=None)
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        v1 = Schedule.objects.get(event=event, version="v1")

        assert speaker not in v1.speakers_concerned


def test_schedule_speakers_concerned_new_talk_in_update(event):
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        TalkSlotFactory(submission=submission, room=room)
        freeze_schedule(event.wip_schedule, "v2", notify_speakers=False)
        v2 = Schedule.objects.get(event=event, version="v2")

        matched_speaker = [s for s in v2.speakers_concerned if s.user == speaker.user]
        assert len(matched_speaker) == 1
        assert len(v2.speakers_concerned[matched_speaker[0]]["create"]) == 1


def test_schedule_generate_notifications(event):
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    TalkSlotFactory(submission=submission, room=room)
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        v1 = Schedule.objects.get(event=event, version="v1")

    with scope(event=event):
        mails = generate_notifications(v1)

    assert len(mails) == 1
    assert mails[0].pk is not None


def test_schedule_generate_notifications_ical_localized(event):
    event.locale = "en"
    event.locale_array = "en,de"
    event.save()
    room = RoomFactory(
        event=event, name=LazyI18nString({"en": "Main Hall", "de": "Haupthalle"})
    )
    speaker = SpeakerFactory(event=event)
    speaker.user.locale = "de"
    speaker.user.save()
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    TalkSlotFactory(submission=submission, room=room)
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        v1 = Schedule.objects.get(event=event, version="v1")

    with scope(event=event):
        mails = generate_notifications(v1)

    assert len(mails) == 1
    attachments = mails[0].attachments
    assert len(attachments) == 1
    assert "Haupthalle" in attachments[0]["content"]
    assert "Main Hall" not in attachments[0]["content"]


def test_schedule_generate_notifications_no_speakers(event):
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        v1 = Schedule.objects.get(event=event, version="v1")
        mails = generate_notifications(v1)

    assert mails == []


def test_count_pending_notifications_matches_speaker_count(event):
    room = RoomFactory(event=event)
    speaker_a = SpeakerFactory(event=event)
    speaker_b = SpeakerFactory(event=event)
    submission_a = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission_b = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission_a.speakers.add(speaker_a)
    submission_b.speakers.add(speaker_b)
    TalkSlotFactory(submission=submission_a, room=room)
    TalkSlotFactory(submission=submission_b, room=room)
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        v1 = Schedule.objects.get(event=event, version="v1")

    with scope(event=event):
        assert count_pending_notifications(v1) == 2
