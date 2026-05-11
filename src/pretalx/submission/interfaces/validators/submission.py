# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_slot_count(slot_count, *, event):
    """Slot counts above 1 are only allowed when the event has opted into
    the ``present_multiple_times`` feature flag."""
    if (
        slot_count
        and slot_count != 1
        and not event.get_feature_flag("present_multiple_times")
    ):
        raise ValidationError(_("Slot count may only be 1 in this event."))
