# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

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
