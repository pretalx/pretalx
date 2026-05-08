# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from functools import partial

from django_scopes import scope, scopes_disabled

from pretalx.celery_app import app


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
    from pretalx.event.models import Event  # noqa: PLC0415 -- lazy load for celery
    from pretalx.mail.domain.queue import send_outbox_mails  # noqa: PLC0415
    from pretalx.person.models import User  # noqa: PLC0415

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
