# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_unique_version(version, *, event, exclude_schedule=None):
    """Raise ``ValidationError`` when ``version`` collides with another
    schedule version of the same event (case-insensitive).

    ``exclude_schedule`` is for the editing case: an unchanged version would
    otherwise collide with the caller's own row.
    """
    if not (version and event):
        return
    qs = event.schedules.filter(version__iexact=version)
    if exclude_schedule is not None and not exclude_schedule._state.adding:
        qs = qs.exclude(pk=exclude_schedule.pk)
    if qs.exists():
        raise ValidationError(
            _("This schedule version was used already, please choose a different one.")
        )
