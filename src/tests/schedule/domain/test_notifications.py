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
from pretalx.schedule.models.slot import SlotType
from pretalx.submission.models import SubmissionStates
from tests.factories import (
    RoomFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _released(event, version):
    return Schedule.objects.select_related("event", "event__cfp").get(
        event=event, version=version
    )


def test_get_notification_date_format():
    result = get_notification_date_format()
    assert "," in result
    assert result.startswith(get_day_month_date_format())


def test_render_notifications_lists_created_and_moved_slots(event):
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

    empty = render_notifications({"create": [], "update": []}, event)
    created = render_notifications({"create": [slot], "update": []}, event)
    updated = render_notifications({"create": [], "update": [moved]}, event)

    assert empty.strip() == ""
    assert submission.title in created
    assert "moved" not in created.lower()
    assert submission.title in updated
    assert "moved" in updated.lower()


@pytest.mark.parametrize(
    "notification_fn",
    (
        pytest.param(get_full_notifications, id="get_full_notifications"),
        pytest.param(get_current_notifications, id="get_current_notifications"),
    ),
)
def test_notifications_list_only_the_speakers_own_released_slots(
    notification_fn, event
):
    speaker = SpeakerFactory(event=event)
    other_speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    slot = TalkSlotFactory(submission=submission, is_visible=True)

    before = notification_fn(speaker, event)
    assert list(before["create"]) == []
    assert before["update"] == []

    freeze_schedule(slot.schedule, "1.0", notify_speakers=False)

    result = notification_fn(speaker, event)
    other = notification_fn(other_speaker, event)
    assert list(result["create"]) == [slot]
    assert result["update"] == []
    assert list(other["create"]) == []
    assert other["update"] == []


def test_get_current_notifications_reports_moves_since_the_previous_release(event):
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    TalkSlotFactory(submission=submission, is_visible=True)
    freeze_schedule(event.wip_schedule, "1.0", notify_speakers=False)
    freeze_schedule(event.wip_schedule, "2.0", notify_speakers=False)

    current = get_current_notifications(speaker, event)
    full = get_full_notifications(speaker, event)

    assert current == {"create": [], "update": []}
    assert [slot.submission for slot in full["create"]] == [submission]
    assert full["update"] == []

    wip_slot = event.wip_schedule.talks.get(submission=submission)
    new_room = RoomFactory(event=event)
    wip_slot.room = new_room
    wip_slot.save()
    freeze_schedule(event.wip_schedule, "3.0", notify_speakers=False)

    result = get_current_notifications(speaker, event)

    assert result["create"] == []
    assert [(m["submission"], m["new_room"]) for m in result["update"]] == [
        (submission, new_room)
    ]


def test_schedule_speakers_concerned_create_covers_scheduled_talks_only(event):
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    TalkSlotFactory(submission=submission, room=room)
    accepted_speaker = SpeakerFactory(event=event)
    accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    accepted.speakers.add(accepted_speaker)
    TalkSlotFactory(
        submission=accepted,
        room=room,
        start=event.datetime_from + dt.timedelta(hours=2),
        end=event.datetime_from + dt.timedelta(hours=3),
    )
    unscheduled_speaker = SpeakerFactory(event=event)
    unscheduled = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    unscheduled.speakers.add(unscheduled_speaker)
    TalkSlotFactory(submission=unscheduled, room=None, start=None, end=None)
    TalkSlotFactory(
        submission=None,
        schedule=event.wip_schedule,
        room=room,
        start=event.datetime_from + dt.timedelta(hours=4),
        end=event.datetime_from + dt.timedelta(hours=5),
        slot_type=SlotType.BREAK,
        description="Coffee Break",
    )
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        v1 = _released(event, "v1")

        assert v1.talks.get(submission=accepted).is_visible is False
        assert {
            concerned: ([slot.submission for slot in data["create"]], data["update"])
            for concerned, data in v1.speakers_concerned.items()
        } == {speaker: ([submission], []), accepted_speaker: ([accepted], [])}


def test_schedule_speakers_concerned_update_lists_moves_and_additions_not_cancellations(
    event,
):
    room = RoomFactory(event=event)
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission.speakers.add(speaker)
    TalkSlotFactory(submission=submission, room=room)
    new_speaker = SpeakerFactory(event=event)
    new_submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    new_submission.speakers.add(new_speaker)
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        wip_slot = event.wip_schedule.talks.get(submission=submission)
        wip_slot.start = event.datetime_from + dt.timedelta(hours=5)
        wip_slot.end = event.datetime_from + dt.timedelta(hours=6)
        wip_slot.save()
        TalkSlotFactory(submission=new_submission, room=room)
        freeze_schedule(event.wip_schedule, "v2", notify_speakers=False)
        v2 = _released(event, "v2")

        assert {
            concerned: (
                [slot.submission for slot in data["create"]],
                [moved["submission"] for moved in data["update"]],
            )
            for concerned, data in v2.speakers_concerned.items()
        } == {speaker: ([], [submission]), new_speaker: ([new_submission], [])}

        event.wip_schedule.talks.update(
            room=None, start=None, end=None, is_visible=False
        )
        freeze_schedule(event.wip_schedule, "v3", notify_speakers=False)

        assert _released(event, "v3").speakers_concerned == {}


def test_schedule_generate_notifications_queues_one_mail_per_speaker(event):
    room = RoomFactory(event=event)
    speaker_a = SpeakerFactory(event=event)
    speaker_b = SpeakerFactory(event=event)
    submission_a = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission_b = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    submission_a.speakers.add(speaker_a)
    submission_b.speakers.add(speaker_b)
    TalkSlotFactory(submission=submission_a, room=room)
    TalkSlotFactory(
        submission=submission_b,
        room=room,
        start=event.datetime_from + dt.timedelta(hours=2),
        end=event.datetime_from + dt.timedelta(hours=3),
    )
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        v1 = _released(event, "v1")

        assert count_pending_notifications(v1) == 2

        mails = generate_notifications(v1)

        assert all(mail.pk is not None for mail in mails)
        assert {
            mail.to_speakers.get(): list(mail.submissions.all()) for mail in mails
        } == {speaker_a: [submission_a], speaker_b: [submission_b]}


def test_schedule_generate_notifications_ical_localized(event):
    event.locale = "en"
    event.locales = ["en", "de"]
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
        v1 = _released(event, "v1")

    with scope(event=event):
        mails = generate_notifications(v1)

    assert len(mails) == 1
    attachments = mails[0].attachments
    assert len(attachments) == 1
    assert "Haupthalle" in attachments[0]["content"]
    assert "Main Hall" not in attachments[0]["content"]


def test_schedule_generate_notifications_query_count(event, django_assert_num_queries):
    room = RoomFactory(event=event)
    for _ in range(4):
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        TalkSlotFactory(submission=submission, room=room)
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
        v1 = _released(event, "v1")

    with scope(event=event), django_assert_num_queries(16):
        mails = generate_notifications(v1)

    assert len(mails) == 4


def test_schedule_generate_notifications_skips_empty_and_unreachable_speakers(event):
    with scope(event=event):
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

        assert generate_notifications(_released(event, "v1")) == []

        room = RoomFactory(event=event)
        speaker = SpeakerFactory(event=event, user=None, email=None, name="No Mail")
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        TalkSlotFactory(submission=submission, room=room)
        freeze_schedule(event.wip_schedule, "v2", notify_speakers=False)

        assert generate_notifications(_released(event, "v2")) == []
        assert event.queued_mails.count() == 0
