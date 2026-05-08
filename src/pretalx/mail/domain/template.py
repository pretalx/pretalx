# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.mail.template_phrases import DEFAULT_PHRASES


def template_for_event(event, *, role):
    """Return the event's MailTemplate for ``role``, creating it from
    :mod:`pretalx.mail.template_phrases` defaults if it does not yet exist."""
    subject, text = DEFAULT_PHRASES[role]
    template, __ = event.mail_templates.get_or_create(
        role=role, defaults={"subject": subject, "text": text}
    )
    return template
