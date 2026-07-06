# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from pretalx.common.validators import validate_event_scope_coverage

TEAM_PERMISSION_FIELDS = (
    "can_create_events",
    "can_change_teams",
    "can_change_organiser_settings",
    "can_change_event_settings",
    "can_change_submissions",
    "is_reviewer",
)


def validate_team_event_coverage(*, all_events, limit_events):
    validate_event_scope_coverage(
        all_events=all_events,
        limit_events=limit_events,
        message=_(
            "Please either pick some events for this team, or grant access to all your events!"
        ),
    )


def validate_team_has_permission(data):
    if not any(data.get(field) for field in TEAM_PERMISSION_FIELDS):
        raise ValidationError(_("Please pick at least one permission for this team!"))
