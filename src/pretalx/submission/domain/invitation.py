# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import logging

from pretalx.common.exceptions import SendMailException

logger = logging.getLogger(__name__)


def send_invitation(submission, *, email, sender, orga=False):
    """Invite an additional speaker to a submission by email.

    Idempotent on (submission, email).
    """
    existing = submission.invitations.filter(email__iexact=email).first()
    if existing:
        return existing
    invitation = submission.invitations.create(email=email)
    try:
        invitation.send(_from=sender)
    except SendMailException as exc:
        logger.warning("Failed to send invitation to %s: %s", email, exc)
    submission.log_action(
        "pretalx.submission.invitation.send",
        person=sender,
        orga=orga,
        data={"email": email},
    )
    return invitation
