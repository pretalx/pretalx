# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_event_scope_coverage(*, all_events, limit_events):
    """Shared by teams and API tokens."""
    if not all_events and not limit_events:
        raise ValidationError(
            {
                "limit_events": _(
                    "Please either pick some events, or grant access to all your events!"
                )
            }
        )
