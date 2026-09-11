# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.event.models import Organiser


def organisers_for_user(user, permissions=None):
    """Organisers the user can administer.

    Filter by team permissions by passing a dict like {"can_create_events": True}
    """
    if user.is_administrator:
        return Organiser.objects.all()
    permissions = permissions or {"can_change_organiser_settings": True}
    return Organiser.objects.filter(
        pk__in=user.teams.filter(**permissions).values_list("organiser", flat=True)
    )
