# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import icalendar
import pytest
from django_scopes import scope

from pretalx.common.urls import get_netloc
from pretalx.schedule.domain.ical import (
    build_slot_vevent,
    get_slot_ical,
    get_slots_ical,
    get_speaker_ical,
    get_submission_ical,
    serialize_calendar,
)
from pretalx.schedule.models.slot import TalkSlot
from tests.factories import TalkSlotFactory

pytestmark = pytest.mark.unit


def test_build_slot_vevent_does_not_mutate_calendar_when_incomplete():
    slot = TalkSlot(start=None, end=None, room=None, submission=None)
    cal = icalendar.Calendar()

    build_slot_vevent(slot, cal)

    assert cal.events == []


@pytest.mark.django_db
def test_get_slot_ical_builds_vevent_without_control_characters():
    slot = TalkSlotFactory(
        submission__title="Talk\x1btitle",  # ESC
        submission__abstract="Abstract\x9bwith control",  # 8-bit CSI
    )
    submission = slot.submission

    cal = get_slot_ical(slot)
    serialized = serialize_calendar(cal)

    assert cal["prodid"] == f"-//pretalx//{get_netloc(slot.event)}//{submission.code}"
    vevent = cal.events[0]
    assert vevent["summary"] == f"Talktitle - {submission.display_speaker_names}"
    assert vevent["description"] == "Abstractwith control"
    assert vevent["location"] == str(slot.room.name)
    assert vevent["uid"].startswith(f"pretalx-{slot.event.slug}-{submission.code}@")
    assert vevent.start == slot.local_start
    assert vevent.end == slot.local_end
    assert "BEGIN:VEVENT" in serialized
    assert "\x1b" not in serialized
    assert "\x9b" not in serialized


@pytest.mark.django_db
def test_get_slots_ical_prodid_variants(event, talk_slot):
    netloc = get_netloc(event)
    submission = talk_slot.submission
    speaker = submission.speakers.select_related("event", "user").first()
    with scope(event=event):
        slots = event.wip_schedule.talks.filter(pk=talk_slot.pk).select_related(
            "submission__event", "room"
        )
        plain = get_slots_ical(event, slots)
        suffixed = get_slots_ical(event, slots, prodid_suffix="faved")
        empty = get_slots_ical(event, event.wip_schedule.talks.none())
        for_speaker = get_speaker_ical(event, speaker)
        for_submission = get_submission_ical(submission, slots)

    assert plain["prodid"] == f"-//pretalx//{netloc}//{event.slug}"
    assert len(plain.events) == 1
    assert suffixed["prodid"] == f"-//pretalx//{netloc}//{event.slug}//faved"
    assert for_speaker["prodid"] == (
        f"-//pretalx//{netloc}//{event.slug}//speaker//{speaker.code}"
    )
    assert for_submission["prodid"] == (
        f"-//pretalx//{netloc}//{event.slug}//talk//{submission.code}"
    )
    assert empty.events == []
    assert "BEGIN:VEVENT" not in serialize_calendar(empty)


@pytest.mark.django_db
def test_get_slot_ical_uses_iana_tzid_without_collision_across_calendars():
    slot_london = TalkSlotFactory(submission__event__timezone="Europe/London")
    slot_manila = TalkSlotFactory(submission__event__timezone="Asia/Manila")
    slot_la = TalkSlotFactory(submission__event__timezone="America/Los_Angeles")

    london_result = serialize_calendar(get_slot_ical(slot_london))
    manila_result = serialize_calendar(get_slot_ical(slot_manila))
    la_result = serialize_calendar(get_slot_ical(slot_la))

    assert "DTSTART;TZID=Europe/London:" in london_result
    assert "DTEND;TZID=Europe/London:" in london_result
    assert "TZID:Europe/London" in london_result
    assert "TZID=GMT" not in london_result
    assert "TZID:GMT" not in london_result
    assert "DTSTART;TZID=Asia/Manila:" in manila_result
    assert "TZOFFSETTO:+0800" in manila_result
    assert "DTSTART;TZID=America/Los_Angeles:" in la_result
    assert "TZOFFSETTO:-0800" in la_result
