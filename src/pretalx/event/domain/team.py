# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.event.models import TeamInvite


def create_team_invites(*, team, emails):
    """Create one TeamInvite per email and dispatch the invitation mail."""
    invites = TeamInvite.objects.bulk_create(
        TeamInvite(team=team, email=email) for email in emails
    )
    for invite in invites:
        invite.send()
    return invites
