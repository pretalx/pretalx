# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Raphael Michel

"""Higher-level mail dispatch: signals, audit logging, scheduling
the worker. Raw SMTP delivery lives in :mod:`pretalx.mail.domain.smtp`.
"""

import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from kombu.exceptions import OperationalError

from pretalx.common.exceptions import SendMailException
from pretalx.mail import tasks as mail_tasks
from pretalx.mail.domain.render import (
    assert_rendered,
    delivery_html,
    delivery_text,
    render_to_mail,
)
from pretalx.mail.domain.smtp import to_recipients
from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.signals import (
    queuedmail_post_send,
    queuedmail_pre_send,
    request_pre_send,
)
from pretalx.mail.tasks import task_send_draft

logger = logging.getLogger(__name__)


def get_send_mail_exceptions(request):
    exceptions = [
        result[1]
        for result in request_pre_send.send_robust(
            sender=request.event, request=request
        )
        if len(result) == 2 and isinstance(result[1], SendMailException)
    ]
    if exceptions:
        errors = [str(e) for e in exceptions]
        return errors or [_("You cannot send emails at this time.")]
    return None


def send_draft(mail, *, requestor=None, orga: bool = True) -> None:
    """Hand a saved DRAFT :class:`QueuedMail` to the worker for delivery.

    Requires ``mail.pk``; for unsaved mails see :func:`send_transient`.
    """
    if mail._state.adding:
        raise RuntimeError("send_draft requires a persisted mail")

    if mail.state in (QueuedMailStates.SENT, QueuedMailStates.SENDING):
        raise ValidationError(
            _("This email has been sent already. It cannot be sent again.")
        )

    event = mail.event

    with transaction.atomic():
        if event:
            queuedmail_pre_send.send_robust(sender=event, mail=mail)

        if mail.sent is not None or mail.state == QueuedMailStates.SENT:
            # A pre_send signal handler did the sending; nothing left to do.
            mail.state = QueuedMailStates.SENT
            mail.save(update_fields=["state", "sent"])
            return

        mail.state = QueuedMailStates.SENDING
        mail.error_data = None
        mail.error_timestamp = None
        mail.save(update_fields=["state", "error_data", "error_timestamp"])

    # Dispatch outside the atomic block so the worker observes the
    # SENDING row instead of racing the commit. Do not move this back
    # inside the transaction.
    try:
        task_send_draft.apply_async(args=[mail.pk], ignore_result=True)
    except (OSError, OperationalError) as exc:
        mail.mark_failed(exc)
        return

    mail.log_action(
        "pretalx.mail.sent",
        person=requestor,
        orga=orga,
        data={"to_users": [(user.pk, user.email) for user in mail.to_users.all()]},
    )
    if event:
        queuedmail_post_send.send_robust(sender=event, mail=mail)


def send_transient(mail, *, force_global_backend: bool = False) -> None:
    """Fire-and-forget delivery of an unsaved :class:`QueuedMail`. No
    row, no signals, no log entry.

    Async — renders the body synchronously and schedules
    :func:`task_send_transient`, which calls
    :func:`pretalx.mail.domain.smtp.deliver_payload`. The worker uses
    ``mail.event``'s SMTP for delivery, unless ``force_global_backend=True``
    (system mails: pin to global so delivery survives a broken event SMTP).
    Caller must set ``mail.to`` first. A broker outage is logged and
    swallowed; the in-memory ``mail.sent`` / ``mail.state`` flip is
    best-effort only.
    """
    if not mail._state.adding:
        raise RuntimeError("send_transient must not be called on a persisted mail")

    assert_rendered(mail.subject, mail.text, mail.text_html)

    recipients = to_recipients(mail.to)
    if not recipients:
        raise ValueError("send_transient called with empty mail.to")

    event = None if force_global_backend else mail.event
    try:
        mail_tasks.task_send_transient.apply_async(
            kwargs={
                "to": recipients,
                "subject": mail.prefixed_subject,
                "body": delivery_text(mail),
                "html": delivery_html(mail),
                "reply_to": to_recipients(mail.reply_to),
                "event_id": event.pk if event else None,
                "cc": to_recipients(mail.cc),
                "bcc": to_recipients(mail.bcc),
                "attachments": mail.attachments,
            },
            ignore_result=True,
        )
    except (OSError, OperationalError):
        logger.exception("Failed to queue transient mail to %s", recipients)
        return
    mail.sent = now()
    mail.state = QueuedMailStates.SENT


def send_system_mail(
    *,
    subject,
    text,
    to: str,
    event=None,
    locale=None,
    context_kwargs=None,
    safe_extra_context=None,
):
    """Render and dispatch a *pretalx → user* notification: password
    resets, password / email change confirmations, organiser team
    invites, :func:`pretalx.event.domain.mail.send_orga_mail`.

    Async — defers to :func:`task_send_transient`. Always pins to the
    global backend (a broken event SMTP must not block password resets);
    ``event`` only informs placeholder resolution and body styling. Not
    persisted, not signalled, no audit log.

    Not for event-shaped correspondence (speaker invitations, schedule
    notifications, …) — those want the event's From: line; render via
    :func:`render_to_mail` or :func:`render_template_to_mail` and
    dispatch through :func:`send_draft` (after :func:`save_draft`) or
    :func:`send_transient`.
    """
    mail = render_to_mail(
        subject_template=subject,
        text_template=text,
        event=event,
        locale=locale,
        context_kwargs=context_kwargs,
        safe_extra_context=safe_extra_context,
    )
    mail.to = to
    send_transient(mail, force_global_backend=True)
