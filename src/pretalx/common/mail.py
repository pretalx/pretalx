import logging
from email.utils import formataddr
from smtplib import SMTPResponseException, SMTPSenderRefused

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.mail.backends.smtp import EmailBackend
from inlinestyler.utils import inline_css

from pretalx.celery_app import app
from pretalx.event.models import Event

logger = logging.getLogger(__name__)


class CustomSMTPBackend(EmailBackend):
    def test(self, from_addr):
        try:
            self.open()
            self.connection.ehlo_or_helo_if_needed()
            (code, resp) = self.connection.mail(from_addr, [])
            if code != 250:
                logger.warning(
                    f'Error testing mail settings, code {code}, resp: {resp}'
                )
                raise SMTPSenderRefused(code, resp)
            (code, resp) = self.connection.rcpt('test@example.com')
            if code not in (250, 251):
                logger.warning(
                    f'Error testing mail settings, code {code}, resp: {resp}'
                )
                raise SMTPSenderRefused(code, resp)
        finally:
            self.close()


class TolerantDict(dict):
    def __missing__(self, key):
        """Don't fail when formatting strings with a dict with missing keys."""
        return key


class SendMailException(Exception):
    pass


@app.task(bind=True)
def mail_send_task(
    self,
    to: str,
    subject: str,
    body: str,
    html: str,
    reply_to: list = None,
    event: int = None,
    cc: list = None,
    bcc: list = None,
    headers: dict = None,
):
    headers = headers or dict()
    if reply_to and isinstance(reply_to, str):
        reply_to = reply_to.split(',')
    if event:
        event = Event.objects.get(pk=event)
        backend = event.get_mail_backend()
        sender = event.settings.get('mail_from')
        reply_to = reply_to or event.settings.get('mail_reply_to')
        if not sender or sender == 'noreply@example.org':
            reply_to = reply_to or [formataddr((str(event.name), event.email))]
            sender = settings.MAIL_FROM
        sender = formataddr((str(event.name), sender))
    else:
        sender = formataddr(('pretalx', settings.MAIL_FROM))
        backend = get_connection(fail_silently=False)

    email = EmailMultiAlternatives(
        subject, body, sender, to=to, cc=cc, bcc=bcc, headers=headers, reply_to=reply_to
    )

    if html is not None:
        email.attach_alternative(inline_css(html), 'text/html')

    try:
        backend.send_messages([email])
    except SMTPResponseException as exception:
        # Retry on external problems: Connection issues (101, 111), timeouts (421), filled-up mailboxes (422),
        # out of memory (431), network issues (442), another timeout (447), or too many mails sent (452)
        if exception.smtp_code in (101, 111, 421, 422, 431, 442, 447, 452):
            self.retry(max_retries=5, countdown=2 ** (self.request.retries * 2))
        logger.exception('Error sending email')
        raise SendMailException('Failed to send an email to {}.'.format(to))
    except Exception:
        logger.exception('Error sending email')
        raise SendMailException('Failed to send an email to {}.'.format(to))
