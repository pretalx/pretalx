# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from pretalx.submission.enums import AttendeeSignupStates


def validate_slot_count(slot_count, *, event):
    """Slot counts above 1 are only allowed when the event has opted into
    the ``present_multiple_times`` feature flag."""
    if (
        slot_count
        and slot_count != 1
        and not event.get_feature_flag("present_multiple_times")
    ):
        raise ValidationError(_("Slot count may only be 1 in this event."))


def validate_signup_required(submission, value):
    if value is not False or submission._state.adding:
        return
    from pretalx.submission.models import Submission  # noqa: PLC0415 -- predicate

    persisted = (
        Submission.objects.filter(pk=submission.pk)
        .values_list("attendee_signup_required", flat=True)
        .first()
    )
    if persisted is False:
        return
    if submission.attendee_signups.filter(
        state=AttendeeSignupStates.CONFIRMED
    ).exists():
        raise ValidationError(
            {
                "attendee_signup_required": _(
                    "You cannot disable signup for this session while it still "
                    "has attendee signups."
                )
            },
            code="signups_exist",
        )
