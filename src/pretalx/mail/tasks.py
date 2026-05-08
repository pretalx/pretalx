# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Raphael Michel

import logging
from functools import partial
from smtplib import SMTPResponseException

from django_scopes import scope, scopes_disabled

from pretalx.celery_app import app
from pretalx.common.exceptions import SendMailException

logger = logging.getLogger(__name__)


# SMTP response codes worth retrying: connection issues (101, 111), timeouts
# (421, 447), filled-up mailboxes (422), out of memory (431), network issues
# (442), too many mails sent (452).
_RETRYABLE_SMTP_CODES = frozenset({101, 111, 421, 422, 431, 442, 447, 452})


@app.task(bind=True, name="pretalx.common.send_mail")
def mail_send_task(
    self,
    to,
    subject,
    body,
    html,
    reply_to=None,
    event=None,
    cc=None,
    bcc=None,
    headers=None,
    attachments=None,
    queued_mail_id=None,
):
    """Send a single email via the appropriate backend.

    Thin wrapper around :mod:`pretalx.mail.domain.send`: it handles the
    Celery-side concerns (event lookup, retry, marking the queued mail
    sent/failed) while the message construction itself lives in domain.
    """
    from pretalx.event.models import Event  # noqa: PLC0415 -- avoid circular import
    from pretalx.mail.domain.send import (  # noqa: PLC0415 -- avoid circular import
        build_message,
        filter_recipients,
        resolve_envelope,
    )

    to = filter_recipients(to)
    if not to:
        return

    event_obj = Event.objects.get(pk=event) if event else None
    sender, reply_to, backend = resolve_envelope(event_obj, reply_to)

    email = build_message(
        to=to,
        subject=subject,
        body=body,
        html=html,
        reply_to=reply_to,
        sender=sender,
        cc=cc,
        bcc=bcc,
        headers=headers,
        attachments=attachments,
    )

    try:
        backend.send_messages([email])
    except SMTPResponseException as exception:
        if exception.smtp_code in _RETRYABLE_SMTP_CODES:
            try:
                self.retry(max_retries=5, countdown=2 ** (self.request.retries * 2))
            except self.MaxRetriesExceededError:
                if queued_mail_id:
                    _mark_queued_mail_failed(queued_mail_id, exception)
                    return
                raise
        logger.exception("Error sending email")
        if queued_mail_id:
            _mark_queued_mail_failed(queued_mail_id, exception)
            return
        raise SendMailException(
            f"Failed to send an email to {to}: {exception}"
        ) from exception
    except Exception as exception:
        logger.exception("Error sending email")
        if queued_mail_id:
            _mark_queued_mail_failed(queued_mail_id, exception)
            return
        raise SendMailException(
            f"Failed to send an email to {to}: {exception}"
        ) from exception
    else:
        if queued_mail_id:
            _mark_queued_mail_sent(queued_mail_id)


@scopes_disabled()
def _mark_queued_mail_sent(queued_mail_id):
    from pretalx.mail.models import QueuedMail  # noqa: PLC0415 -- avoid circular import

    try:
        QueuedMail.objects.get(pk=queued_mail_id).mark_sent()
    except QueuedMail.DoesNotExist:
        logger.warning("QueuedMail %s not found for marking as sent", queued_mail_id)


@scopes_disabled()
def _mark_queued_mail_failed(queued_mail_id, exception):
    from pretalx.mail.models import QueuedMail  # noqa: PLC0415 -- avoid circular import

    try:
        QueuedMail.objects.get(pk=queued_mail_id).mark_failed(exception)
    except QueuedMail.DoesNotExist:
        logger.warning("QueuedMail %s not found for marking as failed", queued_mail_id)


def progress_callback(task, current, total):
    task.update_state(
        state="PROGRESS",
        meta={
            "value": round(current / total * 100),
            "current": current,
            "total": total,
        },
    )


@app.task(bind=True, name="pretalx.mail.generate_mails")
def task_create_mails_for_template(
    self, *, template_id, recipients, skip_queue=False, **kwargs
):
    """Generate (and optionally send) emails from a template for a list of recipients.

    ``**kwargs`` swallows legacy parameters from in-flight tasks queued by
    older deploys (notably ``event_id``); drop in 2027.
    """
    from pretalx.mail.domain.queue import create_mails_for_template  # noqa: PLC0415
    from pretalx.mail.models import MailTemplate  # noqa: PLC0415

    with scopes_disabled():
        template = MailTemplate.objects.select_related("event").get(pk=template_id)

    with scope(event=template.event):
        return create_mails_for_template(
            template,
            recipients=recipients,
            skip_queue=skip_queue,
            progress=partial(progress_callback, self),
        )


@app.task(bind=True, name="pretalx.mail.send_outbox_mails")
def task_send_outbox_mails(self, *, event_id, mail_pks, requestor_id=None):
    """Send a batch of queued mails from the outbox."""
    from pretalx.event.models import Event  # noqa: PLC0415 -- avoid circular import
    from pretalx.mail.domain.queue import send_outbox_mails  # noqa: PLC0415
    from pretalx.person.models import User  # noqa: PLC0415 -- avoid circular import

    with scopes_disabled():
        event = Event.objects.get(pk=event_id)
        requestor = (
            User.objects.filter(pk=requestor_id).first() if requestor_id else None
        )

    with scope(event=event):
        return send_outbox_mails(
            event=event,
            mail_pks=mail_pks,
            requestor=requestor,
            progress=partial(progress_callback, self),
        )
