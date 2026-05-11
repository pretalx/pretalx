# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.mail.template_phrases import DEFAULT_PHRASES


def mail_template_by_role(event, role):
    """Return the :class:`MailTemplate` for ``role`` on ``event``, creating
    it from the localised default phrases if the row does not exist yet.

    Used both during event initialisation and at every send site, so that
    deleting a role-bound template (e.g. through the orga UI) recreates
    a usable default rather than crashing the next send.
    """
    subject, text = DEFAULT_PHRASES[role]
    template, __ = event.mail_templates.get_or_create(
        role=role, defaults={"subject": subject, "text": text}
    )
    return template
