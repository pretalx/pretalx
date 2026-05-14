# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import logging

from django.db import transaction

from pretalx.common.exceptions import SendMailException
from pretalx.common.text.phrases import phrases
from pretalx.mail.domain.render import render_to_mail
from pretalx.mail.domain.send import send_transient

logger = logging.getLogger(__name__)


def send_invitation(submission, *, email, sender, orga=False):
    """Invite an additional speaker to a submission by email.

    Creates the invitation row, dispatches the invitation mail and logs
    the action. Idempotent on (submission, email): re-inviting the same
    address returns the existing invitation without re-sending or
    re-logging. ``SendMailException`` during dispatch is swallowed so
    the row and log entry remain for the operator to inspect; resending
    requires retracting and reinviting.
    """
    existing = submission.invitations.filter(email__iexact=email).first()
    if existing:
        return existing
    invitation = submission.invitations.create(email=email)
    try:
        mail = render_to_mail(
            subject_template=phrases.cfp.invite_subject,
            text_template=phrases.cfp.invite_text,
            event=submission.event,
            locale=submission.get_email_locale(),
            safe_extra_context={"url": invitation.urls.base},
            context_kwargs={"submission": submission, "inviting_user": sender},
        )
        mail.to = invitation.email
        send_transient(mail)
    except SendMailException as exc:
        logger.warning("Failed to send invitation to %s: %s", email, exc)
    submission.log_action(
        "pretalx.submission.invitation.send",
        person=sender,
        orga=orga,
        data={"email": email},
    )
    return invitation


def retract_invitation(invitation, *, person=None, orga=False):
    """Delete a speaker invitation and log the retraction against its
    parent submission."""
    email = invitation.email
    submission = invitation.submission
    invitation.delete()
    submission.log_action(
        "pretalx.submission.invitation.retract",
        person=person,
        orga=orga,
        data={"email": email},
    )


@transaction.atomic
def accept_invitation(invitation, *, user):
    from pretalx.submission.domain.submission import (  # noqa: PLC0415 -- circular import
        add_speaker,
    )

    submission = invitation.submission
    add_speaker(submission, user=user)
    submission.log_action(
        "pretalx.submission.invitation.accept",
        person=user,
        data={"email": invitation.email},
    )
    invitation.delete()
    return submission
