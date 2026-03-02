# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from zoneinfo import ZoneInfo

import pytest
import vobject.icalendar as ical_module
from django_scopes import scope

from pretalx.schedule.ical import (
    get_slot_ical,
    get_slots_ical,
    get_speaker_ical,
    get_submission_ical,
    patch_out_timezone_cache,
)

pytestmark = pytest.mark.unit


def test_patch_out_timezone_cache_preserves_utc():
    original_utc = ical_module.__tzidMap.get("UTC")
    with patch_out_timezone_cache(ZoneInfo("UTC")):
        pass

    assert ical_module.__tzidMap.get("UTC") == original_utc


def test_patch_out_timezone_cache_clears_non_utc():
    with patch_out_timezone_cache(ZoneInfo("UTC")):
        ical_module.__tzidMap["Fake/Zone"] = "something"

    assert "Fake/Zone" not in ical_module.__tzidMap


def test_patch_out_timezone_cache_handles_missing_utc():
    saved = dict(ical_module.__tzidMap)
    try:
        ical_module.__tzidMap.pop("UTC", None)
        with patch_out_timezone_cache(ZoneInfo("UTC")):
            ical_module.__tzidMap["Test/Zone"] = "test"
        assert "Test/Zone" not in ical_module.__tzidMap
    finally:
        ical_module.__tzidMap = saved


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
