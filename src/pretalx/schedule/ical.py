# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
from contextlib import contextmanager
from zoneinfo import ZoneInfo

from pretalx.common.urls import get_netloc


@contextmanager
def patch_out_timezone_cache(tzinfo):
    """Context manager to clear vobject's timezone cache during ICS generation.

    This prevents vobject from using cached ambiguous timezone abbreviations like "PST"
    which could be interpreted as either Pacific Standard Time (-08:00) or
    Philippine Standard Time (+08:00). By clearing the cache, vobject is forced to
    re-register timezones every time.
    """
    import vobject.icalendar as ical  # noqa: PLC0415

    try:
        minimal_tzid_map = {"UTC": ical.__tzidMap["UTC"]}  # noqa: SLF001 -- patch upstream bug
    except KeyError:
        minimal_tzid_map = {}

    try:
        yield
    finally:
        ical.__tzidMap = minimal_tzid_map  # noqa: SLF001 -- patch upstream bug


def get_slots_ical(event, slots, prodid_suffix=None):
    import vobject  # noqa: PLC0415

    cal = vobject.iCalendar()
    netloc = get_netloc(event)
    prodid = f"-//pretalx//{netloc}//{event.slug}"
    if prodid_suffix:
        prodid = f"{prodid}//{prodid_suffix}"
    cal.add("prodid").value = prodid
    creation_time = dt.datetime.now(ZoneInfo("UTC"))
    for slot in slots:
        slot.build_ical(cal, creation_time=creation_time, netloc=netloc)
    return cal


def get_speaker_ical(event, speaker):
    return get_slots_ical(
        event, speaker.current_talk_slots, prodid_suffix=f"speaker//{speaker.code}"
    )


def get_submission_ical(submission, slots):
    return get_slots_ical(
        submission.event, slots, prodid_suffix=f"talk//{submission.code}"
    )


def get_slot_ical(slot):
    import vobject  # noqa: PLC0415

    cal = vobject.iCalendar()
    netloc = get_netloc(slot.event)
    cal.add("prodid").value = f"-//pretalx//{netloc}//{slot.submission.code or slot.pk}"
    slot.build_ical(cal, netloc=netloc)
    return cal
