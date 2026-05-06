# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from contextlib import suppress

from django.db import models, transaction
from django.db.utils import DatabaseError
from django.utils.timezone import now

from pretalx.schedule.domain.changes import update_unreleased_schedule_changes
from pretalx.schedule.enums import SlotType
from pretalx.schedule.models import Schedule, TalkSlot
from pretalx.schedule.signals import schedule_release
from pretalx.submission.enums import SubmissionStates


def guess_schedule_version(event):
    if not event.current_schedule:
        return "0.1"

    version = event.current_schedule.version
    prefix = ""
    separator = ""
    for separator in (",", ".", "-", "_"):
        if separator in version:
            prefix, version = version.rsplit(separator, maxsplit=1)
            break
    if version.isdigit():
        version = str(int(version) + 1)
        return prefix + separator + version
    return ""


def freeze_schedule(schedule, name, user=None, notify_speakers=True, comment=None):
    """Freeze a schedule as a new version."""

    if name in ("wip", "latest"):
        raise ValueError(f'Cannot use reserved name "{name}" for schedule version.')
    if schedule.version:
        raise ValueError(
            f'Cannot freeze schedule version: already versioned as "{schedule.version}".'
        )
    if not name:
        raise ValueError("Cannot create schedule version without a version name.")

    with transaction.atomic():
        schedule.version = name
        schedule.comment = comment
        schedule.published = now()

        # Create the new WIP first to dodge race conditions on event.wip_schedule.
        wip_schedule = Schedule.objects.create(event=schedule.event)

        schedule.save(update_fields=["published", "version", "comment"])
        schedule.log_action("pretalx.schedule.release", person=user, orga=True)

        # Confirmed submissions and breaks are visible; blockers stay hidden.
        schedule.talks.all().update(is_visible=False)
        schedule.talks.filter(
            models.Q(submission__state=SubmissionStates.CONFIRMED)
            | models.Q(slot_type=SlotType.BREAK),
            start__isnull=False,
        ).update(is_visible=True)

        talks = [
            talk.copy_to_schedule(wip_schedule, save=False)
            for talk in schedule.talks.select_related("submission", "room").all()
        ]
        TalkSlot.objects.bulk_create(talks)

        # Blockers should only exist in WIP, never in a released schedule.
        schedule.talks.filter(slot_type=SlotType.BLOCKER).delete()

    if notify_speakers:
        schedule = schedule.__class__.objects.get(pk=schedule.pk)
        schedule.generate_notifications(save=True)

    with suppress(AttributeError):
        del wip_schedule.event.wip_schedule
    with suppress(AttributeError):
        del wip_schedule.event.current_schedule

    schedule_release.send_robust(schedule.event, schedule=schedule, user=user)

    update_unreleased_schedule_changes(schedule.event, False)

    return schedule, wip_schedule


def unfreeze_schedule(schedule, user=None):
    """Resets the current WIP schedule to an older schedule version."""
    if not schedule.version:
        raise ValueError("Cannot unfreeze schedule version: not released yet.")

    submission_ids = schedule.talks.all().values_list("submission_id", flat=True)
    talks = schedule.event.wip_schedule.talks.exclude(submission_id__in=submission_ids)
    try:
        # Force evaluation to catch the DatabaseError early.
        talks = list(talks.union(schedule.talks.all()))
    except DatabaseError:  # pragma: no cover -- vendor-specific SQLite workaround
        talks = set(talks) | set(schedule.talks.all())

    with transaction.atomic():
        wip_schedule = Schedule.objects.create(event=schedule.event)
        new_talks = [talk.copy_to_schedule(wip_schedule, save=False) for talk in talks]
        TalkSlot.objects.bulk_create(new_talks)

        schedule.event.wip_schedule.talks.all().delete()
        schedule.event.wip_schedule.delete()

    update_unreleased_schedule_changes(schedule.event, False)

    with suppress(AttributeError):
        del wip_schedule.event.wip_schedule

    return schedule, wip_schedule
