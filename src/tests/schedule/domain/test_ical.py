# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import icalendar
import pytest
from django_scopes import scope

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
def test_build_slot_vevent_appends_vevent():
    slot = TalkSlotFactory()

    cal = icalendar.Calendar()
    build_slot_vevent(slot, cal)

    vevent = cal.events[0]
    assert (
        vevent["summary"]
        == f"{slot.submission.title} - {slot.submission.display_speaker_names}"
    )
    assert vevent["location"] == str(slot.room.name)
    assert vevent.start == slot.local_start
    assert vevent.end == slot.local_end


@pytest.mark.django_db
def test_get_slots_ical_with_slot(event, talk_slot):
    with scope(event=event):
        slots = event.wip_schedule.talks.filter(pk=talk_slot.pk)
        cal = get_slots_ical(event, slots)

    result = serialize_calendar(cal)
    assert "BEGIN:VCALENDAR" in result
    assert "BEGIN:VEVENT" in result
    assert event.slug in cal["prodid"]


@pytest.mark.django_db
def test_get_slots_ical_prodid_with_suffix(event, talk_slot):
    with scope(event=event):
        slots = event.wip_schedule.talks.filter(pk=talk_slot.pk)
        cal = get_slots_ical(event, slots, prodid_suffix="faved")

    assert cal["prodid"].endswith("//faved")


@pytest.mark.django_db
def test_get_slots_ical_empty_slots(event):
    with scope(event=event):
        slots = event.wip_schedule.talks.none()
        cal = get_slots_ical(event, slots)

    result = serialize_calendar(cal)
    assert "BEGIN:VCALENDAR" in result
    assert "BEGIN:VEVENT" not in result


@pytest.mark.django_db
def test_get_slot_ical_uses_iana_tzid():
    slot = TalkSlotFactory(submission__event__timezone="Europe/London")

    result = serialize_calendar(get_slot_ical(slot))

    assert "DTSTART;TZID=Europe/London:" in result
    assert "DTEND;TZID=Europe/London:" in result
    assert "TZID:Europe/London" in result
    assert "TZID=GMT" not in result
    assert "TZID:GMT" not in result


@pytest.mark.django_db
def test_get_slot_ical_no_tzid_collision_across_calendars():
    slot_manila = TalkSlotFactory(submission__event__timezone="Asia/Manila")
    slot_la = TalkSlotFactory(submission__event__timezone="America/Los_Angeles")

    manila_result = serialize_calendar(get_slot_ical(slot_manila))
    la_result = serialize_calendar(get_slot_ical(slot_la))

    assert "DTSTART;TZID=Asia/Manila:" in manila_result
    assert "TZOFFSETTO:+0800" in manila_result
    assert "DTSTART;TZID=America/Los_Angeles:" in la_result
    assert "TZOFFSETTO:-0800" in la_result


@pytest.mark.django_db
def test_get_slot_ical(event, talk_slot):
    cal = get_slot_ical(talk_slot)

    result = serialize_calendar(cal)
    assert "BEGIN:VCALENDAR" in result
    assert "BEGIN:VEVENT" in result
    assert talk_slot.submission.code in cal["prodid"]


@pytest.mark.django_db
def test_get_speaker_ical(event, talk_slot):
    speaker = talk_slot.submission.speakers.first()
    cal = get_speaker_ical(event, speaker)

    assert f"speaker//{speaker.code}" in cal["prodid"]


@pytest.mark.django_db
def test_get_submission_ical(event, talk_slot):
    with scope(event=event):
        slots = event.wip_schedule.talks.filter(pk=talk_slot.pk)
        cal = get_submission_ical(talk_slot.submission, slots)

    assert f"talk//{talk_slot.submission.code}" in cal["prodid"]


@pytest.mark.django_db
def test_build_slot_vevent_strips_control_characters():
    slot = TalkSlotFactory(
        submission__title="Talk\x1btitle",  # ESC
        submission__abstract="Abstract\x9bwith control",  # 8-bit CSI
    )

    cal = icalendar.Calendar()
    build_slot_vevent(slot, cal)

    serialized = serialize_calendar(cal)
    assert "\x1b" not in serialized
    assert "\x9b" not in serialized
    assert "Talktitle" in cal.events[0]["summary"]
    assert "Abstractwith control" in cal.events[0]["description"]
