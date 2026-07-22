# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
from zoneinfo import ZoneInfo

from pretalx.common.text.xml import strip_control_characters
from pretalx.common.urls import get_netloc


def get_calendar(event, prodid):
    """Build an empty iCalendar tagged with `-//pretalx//{netloc}//{prodid}`.

    `prodid` is used by calendar clients for de-duplication, so it should be
    stable for the same logical export and distinct between exports.
    """
    import icalendar  # noqa: PLC0415 -- slow import

    cal = icalendar.Calendar()
    cal.add("version", "2.0")
    cal.add("prodid", f"-//pretalx//{get_netloc(event)}//{prodid}")
    return cal


def build_slot_vevent(slot, calendar, *, creation_time=None, netloc=None):
    """Append a VEVENT for *slot* to *calendar*. No-op if the slot is incomplete."""
    if not slot.start or not slot.local_end or not slot.room or not slot.submission:
        return
    import icalendar  # noqa: PLC0415 -- slow import

    creation_time = creation_time or dt.datetime.now(ZoneInfo("UTC"))
    netloc = netloc or get_netloc(slot.event)

    vevent = icalendar.Event()
    vevent.add(
        "summary",
        strip_control_characters(
            f"{slot.submission.title} - {slot.submission.display_speaker_names}"
        ),
    )
    vevent.add("dtstamp", creation_time)
    vevent.add("location", strip_control_characters(slot.room.name))
    vevent.add(
        "uid",
        f"pretalx-{slot.submission.event.slug}-{slot.submission.code}{slot.id_suffix}@{netloc}",
    )
    vevent.add("dtstart", slot.local_start)
    vevent.add("dtend", slot.local_end)
    vevent.add("description", strip_control_characters(slot.submission.abstract))
    vevent.add("url", slot.submission.urls.public.full())
    calendar.add_component(vevent)


def serialize_calendar(calendar):
    if events := calendar.events:
        # icalendar includes 1970-2038 tz data by default, which is
        # *slightly* overkill for non-repeating event data
        timezone_range_padding = dt.timedelta(days=365)
        calendar.add_missing_timezones(
            first_date=(
                min(event.start for event in events) - timezone_range_padding
            ).date(),
            last_date=(
                max(event.end for event in events) + timezone_range_padding
            ).date(),
        )
        for timezone in calendar.timezones:
            # Drop useless comment
            timezone.pop("comment", None)
    return calendar.to_ical().decode()


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
