# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Count

from pretalx.event.models import Organiser


def organisers_for_user(user):
    """Organisers the user can administer, annotated with event and team counts."""
    if user.is_administrator:
        organisers = Organiser.objects.all()
    else:
        organisers = Organiser.objects.filter(
            pk__in={
                team.organiser_id
                for team in user.teams.filter(can_change_organiser_settings=True)
            }
        )
    return organisers.annotate(
        event_count=Count("events", distinct=True),
        team_count=Count("teams", distinct=True),
    )
