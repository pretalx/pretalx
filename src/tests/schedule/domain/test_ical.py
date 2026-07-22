# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
import vobject
import vobject.icalendar as ical_module
from django_scopes import scope

from pretalx.schedule.domain.ical import (
    build_slot_vevent,
    get_slot_ical,
    get_slots_ical,
    get_speaker_ical,
    get_submission_ical,
    patch_vobject_pick_tzid,
)
from pretalx.schedule.models.slot import TalkSlot
from tests.factories import TalkSlotFactory

pytestmark = pytest.mark.unit


def test_build_slot_vevent_does_not_mutate_calendar_when_incomplete():
    slot = TalkSlot(start=None, end=None, room=None, submission=None)
    cal = vobject.iCalendar()

    build_slot_vevent(slot, cal)

    assert "vevent" not in cal.contents


@pytest.mark.django_db
def test_build_slot_vevent_appends_vevent():
    slot = TalkSlotFactory()

    cal = vobject.iCalendar()
    build_slot_vevent(slot, cal)

    vevent = cal.vevent
    assert (
        vevent.summary.value
        == f"{slot.submission.title} - {slot.submission.display_speaker_names}"
    )
    assert vevent.location.value == str(slot.room.name)
    assert vevent.dtstart.value == slot.local_start
    assert vevent.dtend.value == slot.local_end


@pytest.mark.django_db
def test_get_slots_ical_with_slot(event, talk_slot):
    with scope(event=event):
        slots = event.wip_schedule.talks.filter(pk=talk_slot.pk)
        cal = get_slots_ical(event, slots)

    result = cal.serialize()
    assert "BEGIN:VCALENDAR" in result
    assert "BEGIN:VEVENT" in result
    prodid = list(cal.contents["prodid"])[0].value
    assert event.slug in prodid


@pytest.mark.django_db
def test_get_slots_ical_prodid_with_suffix(event, talk_slot):
    with scope(event=event):
        slots = event.wip_schedule.talks.filter(pk=talk_slot.pk)
        cal = get_slots_ical(event, slots, prodid_suffix="faved")

    prodid = list(cal.contents["prodid"])[0].value
    assert prodid.endswith("//faved")


@pytest.mark.django_db
def test_get_slots_ical_empty_slots(event):
    with scope(event=event):
        slots = event.wip_schedule.talks.none()
        cal = get_slots_ical(event, slots)

    result = cal.serialize()
    assert "BEGIN:VCALENDAR" in result
    assert "BEGIN:VEVENT" not in result


@pytest.mark.django_db
def test_get_slot_ical_uses_iana_tzid():
    slot = TalkSlotFactory(submission__event__timezone="Europe/London")

    result = get_slot_ical(slot).serialize()

    assert "DTSTART;TZID=Europe/London:" in result
    assert "DTEND;TZID=Europe/London:" in result
    assert "TZID:Europe/London" in result
    assert "TZID=GMT" not in result
    assert "TZID:GMT" not in result


@pytest.mark.django_db
def test_get_slot_ical_no_tzid_collision_across_calendars():
    slot_manila = TalkSlotFactory(submission__event__timezone="Asia/Manila")
    slot_la = TalkSlotFactory(submission__event__timezone="America/Los_Angeles")

    manila_result = get_slot_ical(slot_manila).serialize()
    la_result = get_slot_ical(slot_la).serialize()

    assert "DTSTART;TZID=Asia/Manila:" in manila_result
    assert "TZOFFSETTO:+0800" in manila_result
    assert "DTSTART;TZID=America/Los_Angeles:" in la_result
    assert "TZOFFSETTO:-0800" in la_result


def test_patch_vobject_pick_tzid_applies_only_once():
    patch_vobject_pick_tzid()
    patched = ical_module.TimezoneComponent.pickTzid
    patch_vobject_pick_tzid()

    assert ical_module.TimezoneComponent.pickTzid is patched


@pytest.mark.django_db
def test_get_slot_ical(event, talk_slot):
    cal = get_slot_ical(talk_slot)

    result = cal.serialize()
    assert "BEGIN:VCALENDAR" in result
    assert "BEGIN:VEVENT" in result
    prodid = list(cal.contents["prodid"])[0].value
    assert talk_slot.submission.code in prodid


@pytest.mark.django_db
def test_get_speaker_ical(event, talk_slot):
    speaker = talk_slot.submission.speakers.first()
    cal = get_speaker_ical(event, speaker)

    prodid = list(cal.contents["prodid"])[0].value
    assert f"speaker//{speaker.code}" in prodid


@pytest.mark.django_db
def test_get_submission_ical(event, talk_slot):
    with scope(event=event):
        slots = event.wip_schedule.talks.filter(pk=talk_slot.pk)
        cal = get_submission_ical(talk_slot.submission, slots)

    prodid = list(cal.contents["prodid"])[0].value
    assert f"talk//{talk_slot.submission.code}" in prodid


@pytest.mark.django_db
def test_build_slot_vevent_strips_control_characters():
    slot = TalkSlotFactory(
        submission__title="Talk\x1btitle",  # ESC
        submission__abstract="Abstract\x9bwith control",  # 8-bit CSI
    )

    cal = vobject.iCalendar()
    build_slot_vevent(slot, cal)

    serialized = cal.serialize()
    assert "\x1b" not in serialized
    assert "\x9b" not in serialized
    assert "Talktitle" in cal.vevent.summary.value
    assert "Abstractwith control" in cal.vevent.description.value
