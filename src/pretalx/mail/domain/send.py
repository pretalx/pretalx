# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Raphael Michel

import re
from contextlib import suppress
from email.utils import formataddr, parseaddr

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import transaction
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from pretalx.mail.domain.render import make_html, make_text
from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.signals import queuedmail_post_send, queuedmail_pre_send

DEBUG_DOMAINS = ["localhost", "example.org", "example.com"]


def _format_email(addr, fallback_name):
    parsed_name, parsed_email = parseaddr(addr)
    return formataddr((parsed_name or fallback_name, parsed_email))


def filter_recipients(to):
    """Normalize ``to`` into a list and drop empty / debug-domain addresses.

    Debug domains (localhost, example.org, example.com) are kept in DEBUG mode
    or when the locmem test backend is active, so dev / CI flows still observe
    the messages.
    """
    if isinstance(to, str):
        to = [to]
    to = [addr for addr in to if addr]
    if (
        not settings.DEBUG
        and settings.EMAIL_BACKEND != "django.core.mail.backends.locmem.EmailBackend"
    ):
        to = [
            addr
            for addr in to
            if not any(addr.endswith(domain) for domain in DEBUG_DOMAINS)
        ]
    return to


def resolve_envelope(event, reply_to):
    """Return ``(sender, reply_to, backend)`` for an outgoing message.

    ``event`` may be ``None`` for system mails. ``reply_to`` may be a list, a
    comma-separated string, or falsy; this normalises it to a list and fills in
    the event default when appropriate.
    """
    reply_to = reply_to.split(",") if isinstance(reply_to, str) else (reply_to or [])
    reply_to = [addr for addr in reply_to if addr]

    if event is None:
        return (
            _format_email(settings.MAIL_FROM, "pretalx"),
            reply_to,
            get_connection(fail_silently=False),
        )

    backend = event.get_mail_backend()
    sender = settings.MAIL_FROM
    if event.mail_settings["smtp_use_custom"]:
        sender = event.mail_settings["mail_from"] or sender

    reply_to = reply_to or event.mail_settings["reply_to"]
    if not reply_to and sender == settings.MAIL_FROM:
        reply_to = event.email
    if isinstance(reply_to, str):
        reply_to = [_format_email(reply_to, str(event.name))]

    sender = formataddr((str(event.name), parseaddr(sender)[1]))
    return sender, reply_to, backend


def build_message(
    *,
    to,
    subject,
    body,
    html,
    reply_to,
    sender,
    cc=None,
    bcc=None,
    headers=None,
    attachments=None,
):
    """Build an :class:`EmailMultiAlternatives` ready to be sent.

    HTML alternatives are CSS-inlined; attachments that fail to attach are
    silently skipped (matching the legacy behaviour).
    """
    subject = re.sub(r"[\x00-\x1f\x7f]+", " ", str(subject)).strip()
    email = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=sender,
        to=to,
        cc=cc,
        bcc=bcc,
        headers=headers or {},
        reply_to=reply_to,
    )
    if html is not None:
        import css_inline  # noqa: PLC0415 -- lazy import to reduce startup cost

        inliner = css_inline.CSSInliner(keep_style_tags=False)
        email.attach_alternative(content=inliner.inline(html), mimetype="text/html")

    if attachments:
        for attachment in attachments:
            with suppress(Exception):
                email.attach(
                    attachment["name"],
                    attachment["content"],
                    attachment["content_type"],
                )
    return email


def send_queued_mail(mail, *, requestor=None, orga: bool = True):
    """Dispatch ``mail`` for delivery.

    :param requestor: The user issuing the command. Used for logging.
    :type requestor: :class:`~pretalx.person.models.user.User`
    :param orga: Was this email sent as by a privileged user?
    """
    from pretalx.mail.tasks import mail_send_task  # noqa: PLC0415 -- domain → tasks

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
