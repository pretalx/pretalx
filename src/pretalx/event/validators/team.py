# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

TEAM_PERMISSION_FIELDS = (
    "can_create_events",
    "can_change_teams",
    "can_change_organiser_settings",
    "can_change_event_settings",
    "can_change_submissions",
    "is_reviewer",
)


def validate_team_event_coverage(*, all_events, limit_events):
    """A team must apply to all events or to a specific selection.

    Pre-save check: ``limit_events`` is the m2m payload from the form/
    serializer (a list/queryset of events), not yet saved.
    """
    if not all_events and not limit_events:
        raise ValidationError(
            {
                "limit_events": _(
                    "Please either pick some events for this team, or grant access to all your events!"
                )
            }
        )


def validate_team_has_permission(data):
    """A team must grant at least one permission, otherwise it is inert."""
    if not any(data.get(field) for field in TEAM_PERMISSION_FIELDS):
        raise ValidationError(_("Please pick at least one permission for this team!"))
