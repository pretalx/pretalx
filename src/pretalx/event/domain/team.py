# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.db import transaction
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


def create_team_invite(*, team, email):
    if team.members.filter(email__iexact=email).exists():
        raise ValidationError(_("This user is already a member of the team."))
    if team.invites.filter(email__iexact=email).exists():
        raise ValidationError(_("This user has already been invited to the team."))
    invite = TeamInvite.objects.create(team=team, email=email)
    send_team_invite(invite)
    return invite


@transaction.atomic
def accept_team_invite(invite, *, user):
    # Lock so that an invite can only be used once
    invite = TeamInvite.objects.select_for_update().filter(pk=invite.pk).first()
    if invite is None:
        return
    team = invite.team
    team.members.add(user)
    team.save()
    team.organiser.log_action("pretalx.invite.orga.accept", person=user, orga=True)
    invite.delete()


def retract_team_invite(invite, *, actor):
    team = invite.team
    email = invite.email
    invite.delete()
    team.log_action(
        "pretalx.team.invite.orga.retract",
        person=actor,
        orga=True,
        data={"email": email},
    )


def remove_team_member(*, team, member, actor):
    team.members.remove(member)
    team.log_action(
        "pretalx.team.remove_member",
        person=actor,
        orga=True,
        data={
            "code": member.code,
            "name": member.get_display_name(),
            "email": member.email,
        },
    )
    with scopes_disabled():
        for token in member.api_tokens.active().filter(events__in=team.events):
            update_token_events(token)
