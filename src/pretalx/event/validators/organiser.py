# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.db.models import Count
from django.utils.translation import gettext_lazy as _


def check_access_permissions(organiser, exclude_team=None):
    """Validate that an organiser still has the required team coverage.

    Run inside a transaction after any team or permission change. Raises if
    coverage is broken, returns a list of ``(code, message)`` warnings for
    softer issues that should be surfaced but not block the change.

    Pass ``exclude_team`` to dry-run the deletion of that team.
    """
    warnings = []
    qs = (
        organiser.teams.all()
        .annotate(member_count=Count("members"))
        .filter(member_count__gt=0)
        .prefetch_related("limit_events")
    )
    if exclude_team is not None:
        qs = qs.exclude(pk=exclude_team.pk)
    teams = list(qs)  # Prevent knock-on queries
    if not [t for t in teams if t.can_change_teams]:
        raise ValidationError(
            _(
                "There must be at least one team with the permission to change teams, as otherwise nobody can create new teams or grant permissions to existing teams."
            )
        )
    if not [t for t in teams if t.can_create_events]:
        warnings.append(
            (
                "no_can_create_events",
                _("Nobody on your teams has the permission to create new events."),
            )
        )
    if not [t for t in teams if t.can_change_organiser_settings]:
        warnings.append(
            (
                "no_can_change_organiser_settings",
                _(
                    "Nobody on your teams has the permission to change organiser-level settings."
                ),
            )
        )

    for event in organiser.events.all():
        event_teams = [
            t for t in teams if t.all_events or event in t.limit_events.all()
        ]
        if not event_teams:
            raise ValidationError(
                str(
                    _(
                        "There must be at least one team with access to every event. Currently, nobody has access to {event_name}."
                    )
                ).format(event_name=event.name)
            )
        if not [t for t in event_teams if t.can_change_event_settings]:
            warnings.append(
                (
                    "no_can_change_event_settings",
                    str(
                        _(
                            "Nobody on your teams has the permissions to change settings for the event {event_name}"
                        )
                    ).format(event_name=event.name),
                )
            )
    return warnings
