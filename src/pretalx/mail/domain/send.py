# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from pretalx.common.mail import mail_send_task
from pretalx.mail.domain.render import make_html, make_text
from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.signals import queuedmail_post_send, queuedmail_pre_send


def send_queued_mail(mail, *, requestor=None, orga: bool = True):
    """Dispatch ``mail`` for delivery.

    :param requestor: The user issuing the command. Used for logging.
    :type requestor: :class:`~pretalx.person.models.user.User`
    :param orga: Was this email sent as by a privileged user?
    """
    if mail.state in (QueuedMailStates.SENT, QueuedMailStates.SENDING):
        raise ValidationError(
            _("This email has been sent already. It cannot be sent again.")
        )

    has_event = getattr(mail, "event", None)
    to = mail.to.split(",") if mail.to else []

    with transaction.atomic():
        if mail.id:
            to += [user.email for user in mail.to_users.all()]
            if has_event:
                queuedmail_pre_send.send_robust(sender=mail.event, mail=mail)

        if mail.sent is not None or mail.state == QueuedMailStates.SENT:
            # The pre_send signal must have handled the sending already,
            # so there is nothing left for us to do.
            mail.state = QueuedMailStates.SENT
            mail.save(update_fields=["state", "sent"])
            return

        text = make_text(mail)
        body_html = make_html(mail)

        task_kwargs = {
            "to": to,
            "subject": mail.prefixed_subject,
            "body": text,
            "html": body_html,
            "reply_to": (mail.reply_to or "").split(","),
            "event": mail.event.pk if has_event else None,
            "cc": (mail.cc or "").split(","),
            "bcc": (mail.bcc or "").split(","),
            "attachments": mail.attachments,
        }

        if mail.pk:
            task_kwargs["queued_mail_id"] = mail.pk
            mail.state = QueuedMailStates.SENDING
            mail.error_data = None
            mail.error_timestamp = None
            mail.save(update_fields=["state", "error_data", "error_timestamp"])

            mail.log_action(
                "pretalx.mail.sent",
                person=requestor,
                orga=orga,
                data={
                    "to_users": [(user.pk, user.email) for user in mail.to_users.all()]
                },
            )

    # Dispatch the async task outside the transaction so the worker sees
    # committed state when it picks up the job.
    from kombu.exceptions import (  # noqa: PLC0415 -- only needed in error path
        OperationalError,
    )

    if mail.pk:
        try:
            mail_send_task.apply_async(kwargs=task_kwargs, ignore_result=True)
        except (OSError, OperationalError) as exc:
            mail.mark_failed(exc)
            return

        queuedmail_post_send.send(sender=mail.event, mail=mail)
    else:
        # Non-persisted mail (commit=False fire-and-forget)
        mail_send_task.apply_async(kwargs=task_kwargs, ignore_result=True)
        mail.sent = now()
        mail.state = QueuedMailStates.SENT
