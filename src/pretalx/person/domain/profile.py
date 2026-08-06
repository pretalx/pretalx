# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.utils.crypto import get_random_string
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from pretalx.common.exceptions import SendMailException
from pretalx.mail.domain.queue import save_draft
from pretalx.mail.domain.recipient import Recipient
from pretalx.mail.domain.render import render_to_mail
from pretalx.mail.domain.send import send_draft
from pretalx.person.enums import SpeakerProfileOrigin
from pretalx.person.models import SpeakerProfile


def create_speaker_profile(event, *, name=None, email=None, locale=None, log_user=None):
    """Create a managed, organiser-created speaker profile.

    Invitation sending must be handled separately."""
    if not email and not name:
        raise ValueError("create_speaker_profile() requires an email or a name")
    profile = SpeakerProfile(
        event=event,
        name=name or None,
        email=email or None,
        locale=locale or None,
        origin=SpeakerProfileOrigin.ORGA,
    )
    profile.save()
    profile.log_action(
        "pretalx.speaker.create",
        person=log_user,
        orga=True,
        data={"email": profile.effective_email, "name": profile.get_display_name()},
    )
    return profile


def send_speaker_invite(profile, *, subject, text, submission=None, log_user=None):
    """Set (or rotate) the invite token and dispatch the mail."""
    if profile.user_id:
        raise SendMailException(
            _("This speaker already has an account and needs no invitation.")
        )
    if not profile.effective_email:
        raise SendMailException(
            _(
                "This speaker has no contact email address, so no invitation can be sent."
            )
        )
    if not subject or not text:
        raise ValueError("send_speaker_invite() requires subject and text")

    locale = profile.effective_locale
    if submission:
        locale = submission.get_email_locale(locale)
    context_kwargs = {"user": Recipient(profile)}
    if submission:
        context_kwargs["submission"] = submission

    old_token, old_sent = profile.invitation_token, profile.invitation_sent
    profile.invitation_token = get_random_string(32)
    profile.invitation_sent = now()
    try:
        mail = render_to_mail(
            subject_template=subject,
            text_template=text,
            event=profile.event,
            locale=locale,
            context_kwargs=context_kwargs,
            safe_extra_context={"invitation_link": profile.urls.invitation},
        )
    except (SendMailException, ValueError) as error:
        profile.invitation_token, profile.invitation_sent = old_token, old_sent
        if isinstance(error, ValueError):
            raise SendMailException(f"Invalid invitation text: {error!s}") from error
        raise
    profile.save(update_fields=["invitation_token", "invitation_sent"])
    save_draft(
        mail, to_speakers=[profile], submissions=[submission] if submission else None
    )
    send_draft(mail, requestor=log_user)
    profile.log_action(
        "pretalx.speaker.invite.send",
        person=log_user,
        orga=True,
        data={"email": profile.effective_email},
    )
    return mail


def retract_speaker_invite(profile, *, log_user=None):
    if not profile.invitation_token:
        return
    email = profile.effective_email
    profile.invitation_token = None
    profile.save(update_fields=["invitation_token"])
    profile.log_action(
        "pretalx.speaker.invite.retract",
        person=log_user,
        orga=True,
        data={"email": email},
    )


def apply_speaker_profile_changes(profile, changed_fields):
    """Run the side-effects keyed off the fields a caller just persisted on
    a speaker profile.
    """
    user = profile.user
    if not user:
        return
    if "name" in set(changed_fields) and profile.name and not user.name:
        user.name = profile.name
        user.save(update_fields=["name"])
