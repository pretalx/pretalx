# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import collections

from django.db import transaction

from pretalx.schedule.models import Availability


def replace_availabilities(instance, availabilities):
    """Replace all availabilities for ``instance`` (a Room or SpeakerProfile)
    with the given list, in a single transaction."""
    merged = Availability.union(availabilities)
    field_name = instance.availabilities.field.name
    for avail in merged:
        setattr(avail, field_name, instance)

    with transaction.atomic():
        instance.availabilities.all().delete()
        Availability.objects.bulk_create(merged)


def merged_speaker_availabilities(schedule):
    """Returns a ``{slot_pk: [Availability, ...]}`` dict.

    One pass for the full schedule rather than per-session access
    to cut down on queries.
    """
    event = schedule.event
    speaker_avails = collections.defaultdict(list)
    for avail in event.valid_availabilities.filter(person__isnull=False):
        speaker_avails[avail.person_id].append(avail)

    result = {}
    talks = (
        schedule.talks.filter(submission__isnull=False)
        .select_related("submission")
        .with_sorted_speakers()
    )
    for talk in talks:
        speaker_sets = [
            speaker_avails[speaker.pk]
            for speaker in talk.submission.sorted_speakers
            if speaker_avails[speaker.pk]
        ]
        if len(speaker_sets) == 1:
            result[talk.id] = Availability.union(speaker_sets[0])
        elif speaker_sets:
            result[talk.id] = Availability.intersection(*speaker_sets)
        else:
            result[talk.id] = []
    return result
