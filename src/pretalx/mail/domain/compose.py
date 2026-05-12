# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

"""Composition of ad-hoc mails from a saved template.

Two distinct shapes:

* :func:`send_team_mail` — synchronous fan-out to a list of users (team mails;
  small recipient counts, sent immediately, never queued).
* :func:`build_session_mail_task_data` — serialize per-recipient context for
  :func:`pretalx.mail.tasks.task_create_mails_for_template` (session mails;
  potentially large, async, may queue).
"""

from contextlib import suppress

from pretalx.common.exceptions import SendMailException
from pretalx.mail.domain.render import render_template_to_mail
from pretalx.mail.domain.send import send_transient


def send_team_mail(*, template, event, users):
    sent = []
    for user in users:
        with suppress(SendMailException):
            mail = render_template_to_mail(
                template,
                locale=user.locale,
                context_kwargs={"user": user, "event": event},
            )
            mail.to = user.email
            send_transient(mail)
            sent.append(mail)
    return sent


def build_session_mail_task_data(*, template, recipient_contexts, skip_queue=False):
    recipients = []
    for ctx in recipient_contexts:
        entry = {"user_id": ctx["user"].pk}
        if submission := ctx.get("submission"):
            entry["submission_id"] = submission.pk
        if slot := ctx.get("slot"):
            entry["slot_id"] = slot.pk
        recipients.append(entry)

    return {
        "template_id": template.pk,
        "recipients": recipients,
        "skip_queue": skip_queue,
    }
