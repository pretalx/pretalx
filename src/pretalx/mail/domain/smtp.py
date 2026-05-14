# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Raphael Michel

"""Synchronous SMTP delivery.

The functions in this module push messages over the wire — no signals,
no logging, no retry handling, no async layer. Errors propagate to the
caller, which is expected to be a Celery task that decides whether to
retry, mark a row failed, or surface a :class:`SendMailException`.

For the higher-level orchestration (signals, audit logging, scheduling
the worker task) see :mod:`pretalx.mail.domain.send`.
"""

import re
from contextlib import suppress
from email.utils import formataddr, parseaddr

import css_inline
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.mail.backends.base import BaseEmailBackend

from pretalx.mail.domain.render import delivery_html, delivery_text
from pretalx.mail.smtp import CustomSMTPBackend

DEBUG_DOMAINS = ["localhost", "example.org", "example.com"]


def mail_backend_for_event(event, force_custom: bool = False) -> BaseEmailBackend:
    """Resolve the SMTP backend ``event`` should send through.

    Returns the event's :class:`CustomSMTPBackend` when its mail settings
    opt in (or ``force_custom`` is set, used by the SMTP-test view), and
    the global Django backend otherwise.
    """
    if event.mail_settings["smtp_use_custom"] or force_custom:
        return CustomSMTPBackend(
            host=event.mail_settings["smtp_host"],
            port=event.mail_settings["smtp_port"],
            username=event.mail_settings["smtp_username"],
            password=event.mail_settings["smtp_password"],
            use_tls=event.mail_settings["smtp_use_tls"],
            use_ssl=event.mail_settings["smtp_use_ssl"],
            fail_silently=False,
        )
    return get_connection(fail_silently=False)


def _format_email(addr, fallback_name):
    parsed_name, parsed_email = parseaddr(addr)
    return formataddr((parsed_name or fallback_name, parsed_email))


def to_recipients(value):
    """Split a comma-separated address string into a list of addresses,
    dropping empties.

    Pure normalisation — no debug-domain filtering (use
    :func:`filter_recipients` for that). The seam exists so that ``str``
    can later become a typed email-address class without rewriting every
    call site.
    """
    if not value:
        return []
    return [addr for addr in value.split(",") if addr]


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

    backend = mail_backend_for_event(event)
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


def deliver_payload(
    *,
    event,
    to,
    subject,
    body,
    html,
    reply_to=None,
    cc=None,
    bcc=None,
    attachments=None,
):
    """Synchronously deliver a fully-rendered payload over SMTP.

    ``to`` may be a string or list. After debug-domain filtering an
    empty list is a successful no-op. Routes through ``event``'s SMTP
    backend, or the global one when ``event`` is ``None``.

    Raises whatever the SMTP backend raises; the caller decides whether
    to retry or mark a row failed.
    """
    to = filter_recipients(to)
    if not to:
        return
    sender, reply_to, backend = resolve_envelope(event, reply_to)
    email = build_message(
        to=to,
        subject=subject,
        body=body,
        html=html,
        reply_to=reply_to,
        sender=sender,
        cc=cc,
        bcc=bcc,
        attachments=attachments,
    )
    backend.send_messages([email])


def deliver_persisted(mail):
    """Synchronously deliver a saved :class:`QueuedMail` over SMTP.

    No DB writes, no signals, no logging. Renders the body and pushes it
    via the event's SMTP backend (or the global one for eventless mails).
    Raises whatever the SMTP backend raises.
    """
    recipients = to_recipients(mail.to)
    recipients += [user.email for user in mail.to_users.all()]
    deliver_payload(
        event=mail.event,
        to=recipients,
        subject=mail.prefixed_subject,
        body=delivery_text(mail),
        html=delivery_html(mail),
        reply_to=to_recipients(mail.reply_to),
        cc=to_recipients(mail.cc),
        bcc=to_recipients(mail.bcc),
        attachments=mail.attachments,
    )
