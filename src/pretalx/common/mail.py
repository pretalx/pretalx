# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Raphael Michel

import logging
import re
from contextlib import suppress
from email.utils import formataddr, parseaddr
from smtplib import SMTPResponseException, SMTPSenderRefused

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.mail.backends.smtp import EmailBackend

from pretalx.celery_app import app
from pretalx.common.exceptions import SendMailException
from pretalx.event.models import Event

logger = logging.getLogger(__name__)


class CustomSMTPBackend(EmailBackend):
    def test(self, from_addr):
        try:  # pragma: no cover
            self.open()
            self.connection.ehlo_or_helo_if_needed()
            code, resp = self.connection.mail(from_addr, [])
            if code != 250:
                logger.warning(
                    "Error testing mail settings, code %s, resp: %s", code, resp
                )
                raise SMTPSenderRefused(code, resp, sender=from_addr)
            code, resp = self.connection.rcpt("testdummy@pretalx.com")
            if code not in (250, 251):
                logger.warning(
                    "Error testing mail settings, code %s, resp: %s", code, resp
                )
                raise SMTPSenderRefused(code, resp, sender=from_addr)
        finally:
            self.close()


class TolerantDict(dict):
    def __missing__(self, key):
        """Don't fail when formatting strings with a dict with missing keys."""
        return key


def _format_email(addr, fallback_name):
    parsed_name, parsed_email = parseaddr(addr)
    return formataddr((parsed_name or fallback_name, parsed_email))


DEBUG_DOMAINS = [
    "localhost",
    "example.org",
    "example.com",
]


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
):
    if isinstance(to, str):
        to = [to]
    to = [addr for addr in to if addr]

    if (
        not settings.DEBUG
        and settings.EMAIL_BACKEND != "django.core.mail.backends.locmem.EmailBackend"
    ):
        # We don't want to send emails to localhost or example.org in production,
        # but we'll allow it in development setups for easier testing.
        # However, we do want to "send" mails in test environments where they go
        # to the django test outbox.
        to = [
            addr
            for addr in to
            if not any(addr.endswith(domain) for domain in DEBUG_DOMAINS)
        ]
    if not to:
        return
    reply_to = reply_to.split(",") if isinstance(reply_to, str) else (reply_to or [])
    reply_to = [addr for addr in reply_to if addr]
    reply_to = reply_to or []

    if event:
        event = Event.objects.get(pk=event)
        backend = event.get_mail_backend()

        sender = settings.MAIL_FROM
        if event.mail_settings["smtp_use_custom"]:  # pragma: no cover
            sender = event.mail_settings["mail_from"] or sender

        reply_to = reply_to or event.mail_settings["reply_to"]
        if not reply_to and sender == settings.MAIL_FROM:
            reply_to = event.email

        if isinstance(reply_to, str):
            reply_to = [_format_email(reply_to, str(event.name))]

        sender = formataddr((str(event.name), parseaddr(sender)[1]))

    else:
        sender = _format_email(settings.MAIL_FROM, "pretalx")
        backend = get_connection(fail_silently=False)

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
        import css_inline  # noqa: PLC0415

        inliner = css_inline.CSSInliner(keep_style_tags=False)
        body_html = inliner.inline(html)

        email.attach_alternative(content=body_html, mimetype="text/html")

    if attachments:
        for attachment in attachments:
            with suppress(Exception):
                email.attach(
                    attachment["name"],
                    attachment["content"],
                    attachment["content_type"],
                )

    try:
        backend.send_messages([email])
    except SMTPResponseException as exception:  # pragma: no cover
        # Retry on external problems: Connection issues (101, 111), timeouts (421), filled-up mailboxes (422),
        # out of memory (431), network issues (442), another timeout (447), or too many mails sent (452)
        if exception.smtp_code in (101, 111, 421, 422, 431, 442, 447, 452):
            self.retry(max_retries=5, countdown=2 ** (self.request.retries * 2))
        logger.exception("Error sending email")
        raise SendMailException(
            f"Failed to send an email to {to}: {exception}"
        ) from exception
    except Exception as exception:  # pragma: no cover
        logger.exception("Error sending email")
        raise SendMailException(
            f"Failed to send an email to {to}: {exception}"
        ) from exception
