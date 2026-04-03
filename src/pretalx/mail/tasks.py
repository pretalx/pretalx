# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
import logging
from collections import defaultdict

from django.db import transaction
from django.dispatch import receiver
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.celery_app import app
from pretalx.common.exceptions import SendMailException
from pretalx.common.signals import minimum_interval, periodic_task

logger = logging.getLogger(__name__)


@receiver(signal=periodic_task)
@minimum_interval(minutes_after_success=15)
def mark_stale_sending_mails_as_failed(sender, **kwargs):
    from pretalx.mail.models import (  # noqa: PLC0415 -- avoid circular import
        QueuedMail,
        QueuedMailStates,
    )

    with scopes_disabled():
        cutoff = now() - dt.timedelta(hours=1)
        count = QueuedMail.objects.filter(
            state=QueuedMailStates.SENDING, updated__lt=cutoff
        ).update(
            state=QueuedMailStates.DRAFT,
            error_data={
                "error": "Timed out waiting for delivery confirmation",
                "type": "TimeoutError",
            },
            error_timestamp=now(),
            updated=now(),
        )
        if count:
            logger.warning("Marked %d stale sending mails as failed", count)


@app.task(bind=True, name="pretalx.mail.generate_mails")
def task_generate_mails(self, *, event_id, template_id, recipients, skip_queue=False):
    """Generate (and optionally send) emails from a template for a list of recipients."""
    from pretalx.event.models import Event  # noqa: PLC0415
    from pretalx.mail.models import MailTemplate  # noqa: PLC0415
    from pretalx.person.models import User  # noqa: PLC0415
    from pretalx.schedule.models import TalkSlot  # noqa: PLC0415
    from pretalx.submission.models import Submission  # noqa: PLC0415

    def update_progress(current, total):
        self.update_state(
            state="PROGRESS",
            meta={
                "value": round(current / total * 100),
                "current": current,
                "total": total,
            },
        )

    with scopes_disabled():
        event = Event.objects.get(pk=event_id)
        template = MailTemplate.objects.get(pk=template_id, event=event)

        # Batch-load all referenced objects
        user_ids = {r["user_id"] for r in recipients}
        users_by_id = {u.pk: u for u in User.objects.filter(pk__in=user_ids)}

        sub_ids = {r["submission_id"] for r in recipients if "submission_id" in r}
        subs_by_id = (
            {
                s.pk: s
                for s in Submission.objects.filter(
                    pk__in=sub_ids, event=event
                ).select_related("track", "submission_type", "event")
            }
            if sub_ids
            else {}
        )

        slot_ids = {r["slot_id"] for r in recipients if "slot_id" in r}
        slots_by_id = (
            {
                s.pk: s
                for s in TalkSlot.objects.filter(pk__in=slot_ids, schedule__event=event)
            }
            if slot_ids
            else {}
        )

        total = len(recipients)
        render_failures = 0

        mails_by_user = defaultdict(list)
        for i, entry in enumerate(recipients):
            user = users_by_id.get(entry["user_id"])
            if not user:
                continue
            context = {"user": user}
            if "submission_id" in entry:
                context["submission"] = subs_by_id.get(entry["submission_id"])
            if "slot_id" in entry:
                context["slot"] = slots_by_id.get(entry["slot_id"])

            locale = user.locale
            if submission := context.get("submission"):
                locale = submission.get_email_locale(user.locale)

            try:
                mail = template.to_mail(
                    user=None,
                    event=event,
                    locale=locale,
                    context_kwargs=context,
                    commit=False,
                    allow_empty_address=True,
                )
                mails_by_user[user].append((mail, context))
            except SendMailException:
                render_failures += 1

            update_progress(i + 1, total)

        # Deduplicate and save
        result = []
        with transaction.atomic():
            for user, user_mails in mails_by_user.items():
                mail_dict = defaultdict(list)
                for mail, context in user_mails:
                    mail_dict[(mail.subject, mail.text)].append((mail, context))
                for mail_list in mail_dict.values():
                    mail = mail_list[0][0]
                    mail.save()
                    mail.to_users.add(user)
                    for __, context in mail_list:
                        if submission := context.get("submission"):
                            mail.submissions.add(submission)
                    result.append(mail)

        if skip_queue:
            for mail in result:
                try:
                    mail.send()
                except Exception:
                    logger.exception("Failed to send mail %d", mail.pk)

        return {
            "count": len(result),
            "render_failures": render_failures,
            "skip_queue": skip_queue,
        }


@app.task(bind=True, name="pretalx.mail.send_outbox_mails")
def task_send_outbox_mails(self, *, event_id, mail_pks, requestor_id=None):
    """Send a batch of queued mails from the outbox.

    Each mail's .send() renders text/HTML, sets the state to SENDING,
    and dispatches the SMTP delivery to a separate Celery task. Mails that
    are no longer in DRAFT state are silently skipped.
    """
    from pretalx.event.models import Event  # noqa: PLC0415
    from pretalx.mail.models import QueuedMailStates  # noqa: PLC0415
    from pretalx.person.models import User  # noqa: PLC0415

    with scopes_disabled():
        event = Event.objects.get(pk=event_id)
        requestor = (
            User.objects.filter(pk=requestor_id).first() if requestor_id else None
        )
        mails = list(
            event.queued_mails.filter(pk__in=mail_pks, state=QueuedMailStates.DRAFT)
        )
        total = len(mails)

        for i, mail in enumerate(mails):
            try:
                mail.send(requestor=requestor)
            except Exception:
                logger.exception("Failed to send mail %d", mail.pk)

            self.update_state(
                state="PROGRESS",
                meta={
                    "value": round((i + 1) / total * 100),
                    "current": i + 1,
                    "total": total,
                },
            )

        return {"count": total}
