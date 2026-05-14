# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_unique_submission_type_name(submission_type):
    """Reject duplicate ``SubmissionType.name`` within an event.

    The ``I18nCharField`` stores per-locale dicts, so we compare display
    strings (``str(name)``) rather than filter on the raw JSON: a value
    that round-trips to the same display in any locale is treated as a
    duplicate, matching what users see in dropdowns.
    """
    if not (submission_type.event_id and submission_type.name):
        return
    name = str(submission_type.name)
    siblings = submission_type.event.submission_types.exclude(pk=submission_type.pk)
    if any(str(other.name) == name for other in siblings):
        raise ValidationError(
            {"name": _("You already have a session type by this name!")}
        )
