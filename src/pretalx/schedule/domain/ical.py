# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
from contextlib import contextmanager
from zoneinfo import ZoneInfo

from pretalx.common.text.xml import strip_control_characters
from pretalx.common.urls import get_netloc


@contextmanager
def patch_out_timezone_cache():
    """Context manager to clear vobject's timezone cache during ICS generation.

    This prevents vobject from using cached ambiguous timezone abbreviations like "PST"
    which could be interpreted as either Pacific Standard Time (-08:00) or
    Philippine Standard Time (+08:00). By clearing the cache, vobject is forced to
    re-register timezones every time.
    """
    import vobject.icalendar as ical  # noqa: PLC0415 -- slow import

    try:
        minimal_tzid_map = {"UTC": ical.__tzidMap["UTC"]}  # noqa: SLF001 -- patch upstream bug
    except KeyError:
        minimal_tzid_map = {}

    try:
        yield
    finally:
        ical.__tzidMap = minimal_tzid_map  # noqa: SLF001 -- patch upstream bug


def get_calendar(event, prodid):
    """Build an empty iCalendar tagged with `-//pretalx//{netloc}//{prodid}`.

    `prodid` is used by calendar clients for de-duplication, so it should be
    stable for the same logical export and distinct between exports.
    """
    import vobject  # noqa: PLC0415 -- slow import

    cal = vobject.iCalendar()
    cal.add("prodid").value = f"-//pretalx//{get_netloc(event)}//{prodid}"
    return cal


def build_slot_vevent(slot, calendar, *, creation_time=None, netloc=None):
    """Append a VEVENT for *slot* to *calendar*. No-op if the slot is incomplete."""
    if not slot.start or not slot.local_end or not slot.room or not slot.submission:
        return
    creation_time = creation_time or dt.datetime.now(ZoneInfo("UTC"))
    netloc = netloc or get_netloc(slot.event)

    with patch_out_timezone_cache():
        vevent = calendar.add("vevent")
        vevent.add("summary").value = strip_control_characters(
            f"{slot.submission.title} - {slot.submission.display_speaker_names}"
        )
        vevent.add("dtstamp").value = creation_time
        vevent.add("location").value = strip_control_characters(slot.room.name)
        vevent.add(
            "uid"
        ).value = f"pretalx-{slot.submission.event.slug}-{slot.submission.code}{slot.id_suffix}@{netloc}"

        vevent.add("dtstart").value = slot.local_start
        vevent.add("dtend").value = slot.local_end
        vevent.add("description").value = strip_control_characters(
            slot.submission.abstract
        )
        vevent.add("url").value = slot.submission.urls.public.full()


def get_slots_ical(event, slots, prodid_suffix=None):
    prodid = event.slug
    if prodid_suffix:
        prodid = f"{prodid}//{prodid_suffix}"
    cal = get_calendar(event, prodid)
    creation_time = dt.datetime.now(ZoneInfo("UTC"))
    netloc = get_netloc(event)
    for slot in slots:
        build_slot_vevent(slot, cal, creation_time=creation_time, netloc=netloc)
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
    cal = get_calendar(slot.event, slot.submission.code or slot.pk)
    build_slot_vevent(slot, cal)
    return cal
