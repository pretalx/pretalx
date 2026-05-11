# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.utils.safestring import mark_safe
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _
from django_scopes import scopes_disabled

from pretalx.event.models import TeamInvite
from pretalx.mail.domain.send import send_system_mail
from pretalx.person.domain.auth_token import update_token_events


def send_team_invite(invite):
    # Team invitations are not persisted to an outbox and not logged:
    # the recipient is not yet attached to an organiser, so there is
    # no defensible scope under which a row or audit entry could
    # live. Granting "list mails" access to either the inviter's
    # team or the new team would leak invitation tokens; we sidestep
    # the access-control problem by sending fire-and-forget.
    invitation_text = _("""Hi!
You have been invited to the {name} event organiser team - Please click here to accept:

{invitation_link}

See you there,
The {organiser} team""")
    invitation_subject = _("You have been invited to an organiser team")

    send_system_mail(
        subject=invitation_subject,
        text=invitation_text,
        to=invite.email,
        locale=get_language(),
        safe_extra_context={
            # Team and organiser names are admin-controlled strings
            # that have already passed through Django's form layer.
            "name": mark_safe(str(invite.team.name)),  # noqa: S308  -- organiser-controlled
            "invitation_link": mark_safe(invite.invitation_url),  # noqa: S308  -- internally-built URL
            "organiser": mark_safe(str(invite.team.organiser.name)),  # noqa: S308  -- organiser-controlled
        },
    )


def create_team_invites(*, team, emails):
    """Create one TeamInvite per email and dispatch the invitation mail."""
    invites = TeamInvite.objects.bulk_create(
        TeamInvite(team=team, email=email) for email in emails
    )
    for invite in invites:
        send_team_invite(invite)
    return invites


def remove_team_member(*, team, member):
    """Remove ``member`` from ``team`` and prune their API tokens."""
    team.members.remove(member)
    with scopes_disabled():
        for token in member.api_tokens.active().filter(events__in=team.events):
            update_token_events(token)
