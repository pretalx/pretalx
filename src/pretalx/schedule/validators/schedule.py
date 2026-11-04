# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _


@deconstructible
class ScheduleVersionValidator(RegexValidator):
    regex = r"\A(?!\.\.?\Z)[^/]*\Z"
    message = _("Schedule versions cannot contain slashes or be “.” or “..”.")

    def __call__(self, value):
        if value and value.strip().lower() in ("wip", "latest"):
            raise ValidationError(
                _("This version name is reserved, please choose a different one."),
                code=self.code,
            )
        super().__call__(value)


validate_schedule_version = ScheduleVersionValidator()


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
