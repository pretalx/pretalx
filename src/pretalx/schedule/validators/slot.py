# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_slot_within_event(value, *, event):
    if not value or not event:
        return
    if event.datetime_from and value < event.datetime_from:
        raise ValidationError(_("Scheduled times cannot be before the event starts."))
    if event.datetime_to and value > event.datetime_to:
        raise ValidationError(_("Scheduled times cannot be after the event ends."))


def validate_slot_time_range(*, start, end):
    if start and end and start > end:
        raise ValidationError(_("The end time has to be after the start time."))
