# SPDX-FileCopyrightText: 2024-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from collections import defaultdict

from django.template.loader import get_template
from django.utils.formats import get_format
from django.utils.timezone import override

from pretalx.common.language import get_day_month_date_format, language
from pretalx.mail.domain.template import mail_template_by_role
from pretalx.mail.enums import MailTemplateRoles
from pretalx.person.models import SpeakerProfile
from pretalx.schedule.domain.ical import get_slot_ical


def get_notification_date_format():
    """Call from correct locale context!"""
    return get_day_month_date_format() + ", " + get_format("TIME_FORMAT")


def render_notifications(data, event):
    """Renders the schedule notifications sent to speakers, in the form of a
    Markdown list.

    The data format is expected to be a dict with the keys ``create`` and ``update``,
    each containing a list of TalkSlot objects, as returned by the values of the
    Schedule.speakers.concerned return value."""
    template = get_template("schedule/speaker_notification.txt")
    with override(event.tz):
        date_format = get_notification_date_format()
        return template.render({"START_DATE_FORMAT": date_format, **data})


def get_full_notifications(user, event):
    """Builds a notification dict for a user, pretending that the current schedule
    version is the first one. That is, all talks will be included in the ``create``
    section."""
    if not event.current_schedule:
        return {"create": [], "update": []}
    return {
        "create": event.current_schedule.scheduled_talks.filter(
            submission__speakers__user=user
        ),
        "update": [],
    }


def get_current_notifications(user, event):
    empty_result = {"create": [], "update": []}
    if not event.current_schedule:
        return empty_result
    concerned = event.current_schedule.speakers_concerned
    for profile, data in concerned.items():
        if profile.user_id == user.pk:
            return data
    return empty_result


def compute_speakers_concerned(schedule):
    """Returns a dictionary of speakers with their new and changed talks in
    this schedule.

    Each speaker is assigned a dictionary with ``create`` and
    ``update`` fields, each containing a list of submissions.
    """
    result = {}
    if schedule.changes["action"] == "create":
        for speaker in SpeakerProfile.objects.filter(
            submissions__slots__schedule=schedule
        ):
            talks = schedule.talks.filter(
                submission__speakers=speaker, room__isnull=False, start__isnull=False
            )
            if talks:
                result[speaker] = {"create": talks, "update": []}
        return result

    if schedule.changes["count"] == len(schedule.changes["canceled_talks"]):
        return result

    speakers = defaultdict(lambda: {"create": [], "update": []})
    for new_talk in schedule.changes["new_talks"]:
        for speaker in new_talk.submission.sorted_speakers:
            speakers[speaker]["create"].append(new_talk)
    for moved_talk in schedule.changes["moved_talks"]:
        for speaker in moved_talk["submission"].sorted_speakers:
            speakers[speaker]["update"].append(moved_talk)
    return speakers


def count_pending_notifications(schedule):
    """How many speaker notification mails :func:`generate_notifications`
    would produce for this schedule. One mail per concerned speaker."""
    return len(schedule.speakers_concerned)


def generate_notifications(schedule):
    """Render the per-speaker schedule-change notifications and persist
    each as a DRAFT in the outbox. Returns the list of saved mails."""
    from pretalx.mail.domain.queue import save_draft  # noqa: PLC0415 -- circular import
    from pretalx.mail.domain.render import (  # noqa: PLC0415 -- circular import
        render_template_to_mail,
    )

    mails = []
    # Read via the model so the cached_property is shared with other readers
    # of this schedule instance (e.g. get_current_notifications).
    for speaker, data in schedule.speakers_concerned.items():
        locale = speaker.user.get_locale_for_event(schedule.event)
        slots = list(data.get("create") or []) + [
            talk["new_slot"] for talk in (data.get("update") or [])
        ]
        submissions = [slot.submission for slot in slots if slot]
        with language(locale):
            attachments = [
                {
                    "name": f"{slot.frab_slug}.ics",
                    "content": get_slot_ical(slot).serialize(),
                    "content_type": "text/calendar",
                }
                for slot in slots
            ]
        mail = render_template_to_mail(
            mail_template_by_role(schedule.event, MailTemplateRoles.NEW_SCHEDULE),
            context_kwargs={"user": speaker.user},
            locale=locale,
        )
        save_draft(
            mail,
            to_users=[speaker.user],
            submissions=submissions,
            attachments=attachments,
        )
        mails.append(mail)
    return mails
