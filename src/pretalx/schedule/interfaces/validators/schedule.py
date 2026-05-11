# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_unique_version(schedule):
    if not (schedule.version and schedule.event_id):
        return
    qs = schedule.event.schedules.filter(version__iexact=schedule.version)
    if schedule.pk:
        qs = qs.exclude(pk=schedule.pk)
    if qs.exists():
        raise ValidationError(
            {
                "version": _(
                    "This schedule version was used already, please choose a different one."
                )
            }
        )
