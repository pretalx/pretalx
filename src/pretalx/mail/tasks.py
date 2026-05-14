# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Raphael Michel

import logging
from contextlib import contextmanager, suppress
from functools import partial
from smtplib import SMTPResponseException

from celery.exceptions import Retry
from django_scopes import scope, scopes_disabled

from pretalx.celery_app import app
from pretalx.common.exceptions import SendMailException

logger = logging.getLogger(__name__)


# SMTP response codes worth retrying: connection issues (101, 111), timeouts
# (421, 447), filled-up mailboxes (422), out of memory (431), network issues
# (442), too many mails sent (452).
_RETRYABLE_SMTP_CODES = frozenset({101, 111, 421, 422, 431, 442, 447, 452})


@contextmanager
def retryable_smtp(task):
    """Wrap a synchronous SMTP delivery call with the standard
    retry-then-fail policy. Retryable :class:`SMTPResponseException`
    codes trigger ``task.retry``, which raises :class:`celery.exceptions.Retry`;
    that exception propagates straight through this context manager so
    Celery can reschedule. A budget-exhausted retry, a non-retryable SMTP
    error, or any other exception is logged and re-raised so the caller
    can decide what state the mail should land in (mark a row failed,
    surface a :class:`SendMailException`, …). Callers must therefore
    catch ``Exception`` *excluding* ``Retry``; see :func:`task_send_draft`
    and :func:`task_send_transient`.
    """
    try:
        yield
    except SMTPResponseException as exception:
        if exception.smtp_code in _RETRYABLE_SMTP_CODES:
            # ``task.retry`` raises ``Retry`` on success — that propagates
            # out of this block and out of the contextmanager untouched, so
            # Celery sees it and reschedules. Only ``MaxRetriesExceededError``
            # (budget exhausted) is suppressed; we then fall through to log
            # and re-raise the original SMTP error.
            with suppress(task.MaxRetriesExceededError):
                task.retry(max_retries=5, countdown=2 ** (task.request.retries * 2))
        logger.exception("Error sending email")
        raise
    except Exception:
        logger.exception("Error sending email")
        raise


@app.task(bind=True, name="pretalx.mail.send_draft")
def task_send_draft(self, queued_mail_id):
    """Worker entry point for delivering a persisted ``QueuedMail`` row.

    Loads the row, defers the actual SMTP work to
    :func:`pretalx.mail.domain.smtp.deliver_persisted`, and translates
    the outcome into row-state transitions: success → ``mark_sent``;
    retryable SMTP error → ``self.retry`` (until budget is exhausted,
    then ``mark_failed``); any other failure → ``mark_failed``.
    """
    from pretalx.mail.domain import smtp  # noqa: PLC0415 -- leaf
    from pretalx.mail.models import QueuedMail  # noqa: PLC0415 -- leaf

    with scopes_disabled():
        try:
            mail = QueuedMail.objects.select_related("event").get(pk=queued_mail_id)
        except QueuedMail.DoesNotExist:
            logger.warning("QueuedMail %s not found for dispatch", queued_mail_id)
            return

        try:
            with retryable_smtp(self):
                smtp.deliver_persisted(mail)
        except Retry:
            raise  # task.retry rescheduled us; let Celery handle it.
        except Exception as exception:  # noqa: BLE001 -- terminal failure path: any non-Retry exception → mark_failed
            mail.mark_failed(exception)
        else:
            mail.mark_sent()


@app.task(name="pretalx.common.send_mail")
def mail_send_task(*, queued_mail_id=None, **kwargs):
    """Compatibility shim for the pre-rename task name.

    Workers running new code may still receive jobs queued under the old
    ``pretalx.common.send_mail`` name (in-flight tasks from before the
    deploy). Persisted-mail jobs (those with ``queued_mail_id``) are
    rerouted to :func:`task_send_draft` so the row state stays in sync;
    transient jobs (no ``queued_mail_id``) re-queue under
    :func:`task_send_transient`.

    TODO: delete after the v2026.2.0 release.
    """
    if queued_mail_id is not None:
        task_send_draft.apply_async(args=[queued_mail_id], ignore_result=True)
        return
    kwargs.pop("headers", None)
    if "event" in kwargs:
        kwargs["event_id"] = kwargs.pop("event")
    task_send_transient.apply_async(kwargs=kwargs, ignore_result=True)


@app.task(bind=True, name="pretalx.mail.send_transient")
def task_send_transient(
    self,
    *,
    to,
    subject,
    body,
    html,
    reply_to=None,
    event_id=None,
    cc=None,
    bcc=None,
    attachments=None,
):
    """Worker entry point for delivering a pre-rendered ad-hoc payload
    (system / transient mail: password resets, update notices, plugin
    notifications). No row, no DB writes — defers to
    :func:`pretalx.mail.domain.smtp.deliver_payload` and translates SMTP
    errors into retries / :class:`SendMailException`.
    """
    from pretalx.event.models import Event  # noqa: PLC0415 -- leaf
    from pretalx.mail.domain import smtp  # noqa: PLC0415 -- leaf

    event = Event.objects.get(pk=event_id) if event_id else None
    try:
        with retryable_smtp(self):
            smtp.deliver_payload(
                event=event,
                to=to,
                subject=subject,
                body=body,
                html=html,
                reply_to=reply_to,
                cc=cc,
                bcc=bcc,
                attachments=attachments,
            )
    except Retry:
        raise  # task.retry rescheduled us; let Celery handle it.
    except Exception as exception:
        raise SendMailException(
            f"Failed to send an email to {to}: {exception}"
        ) from exception


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
    from pretalx.mail.domain.queue import bulk_create_drafts  # noqa: PLC0415 -- leaf
    from pretalx.mail.domain.send import send_draft  # noqa: PLC0415 -- leaf
    from pretalx.mail.models import MailTemplate  # noqa: PLC0415 -- leaf

    with scopes_disabled():
        template = MailTemplate.objects.select_related("event").get(pk=template_id)

    with scope(event=template.event):
        saved_mails, render_failures = bulk_create_drafts(
            template, recipients, progress=partial(progress_callback, self)
        )
        if skip_queue:
            for mail in saved_mails:
                try:
                    send_draft(mail)
                except Exception:
                    logger.exception("Failed to send mail %d", mail.pk)

    return {
        "count": len(saved_mails),
        "render_failures": render_failures,
        "skip_queue": skip_queue,
    }


@app.task(bind=True, name="pretalx.mail.send_outbox_mails")
def task_send_outbox_mails(self, *, event_id, mail_pks, requestor_id=None):
    """Send a batch of queued mails from the outbox."""
    from pretalx.event.models import Event  # noqa: PLC0415 -- leaf
    from pretalx.mail.domain.queue import send_outbox_mails  # noqa: PLC0415 -- leaf
    from pretalx.person.models import User  # noqa: PLC0415 -- leaf

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
