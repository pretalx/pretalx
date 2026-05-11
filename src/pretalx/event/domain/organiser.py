# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import transaction
from django_scopes import scope

from pretalx.common.models import ActivityLog
from pretalx.event.domain.event import shred_event
from pretalx.event.models import Organiser, Team


def create_organiser_with_team(*, name, slug, users=None):
    organiser = Organiser.objects.create(name=name, slug=slug)
    team = Team.objects.create(
        organiser=organiser,
        name=f"Team {name}",
        can_create_events=True,
        can_change_teams=True,
        can_change_organiser_settings=True,
    )
    for user in users:
        team.members.add(user)
    return organiser, team


@transaction.atomic
def shred_organiser(organiser, person=None):
    """Irrevocably delete ``organiser`` and all dependent events and data."""
    ActivityLog.objects.create(
        person=person,
        action_type="pretalx.organiser.delete",
        content_object=organiser,
        is_orga_action=True,
        data={"slug": organiser.slug, "name": str(organiser.name)},
    )
    for event in organiser.events.all():
        with scope(event=event):
            shred_event(event, person=person)
    # We keep our logged actions, even with the now-broken content type
    organiser.delete()
