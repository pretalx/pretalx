# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
import logging
from collections import defaultdict
from copy import deepcopy

from django.db import transaction
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.common.exceptions import SendMailException
from pretalx.mail.domain.render import render_template_to_mail
from pretalx.mail.domain.send import send_queued_mail
from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.models import QueuedMail
from pretalx.person.models import User
from pretalx.schedule.models import TalkSlot
from pretalx.submission.models import Submission

logger = logging.getLogger(__name__)


def copy_to_draft(mail):
    """Copy an already sent email to a new draft so the organiser can
    edit and resend it."""
    new_mail = deepcopy(mail)
    new_mail.pk = None
    new_mail.sent = None
    new_mail.state = QueuedMailStates.DRAFT
    new_mail.error_data = None
    new_mail.error_timestamp = None
    new_mail.save()
    new_mail.to_users.set(mail.to_users.all())
    return new_mail


def create_mails_for_template(template, *, recipients, skip_queue=False, progress=None):
    """Render mails from ``template`` for ``recipients`` and persist deduped
    copies. With ``skip_queue=True``, attempt immediate delivery for each.

    ``recipients`` is a sequence of ``{"user_id": int, ["submission_id": int],
    ["slot_id": int]}`` dicts. ``progress`` is an optional ``(current, total)``
    callback.
    """
    event = template.event

    user_ids = {r["user_id"] for r in recipients}
    users_by_id = {u.pk: u for u in User.objects.filter(pk__in=user_ids)}

    sub_ids = {r["submission_id"] for r in recipients if "submission_id" in r}
    subs_by_id = {
        s.pk: s
        for s in Submission.objects.filter(pk__in=sub_ids, event=event).select_related(
            "track", "submission_type", "event"
        )
    }

    slot_ids = {r["slot_id"] for r in recipients if "slot_id" in r}
    slots_by_id = {
        s.pk: s for s in TalkSlot.objects.filter(pk__in=slot_ids, schedule__event=event)
    }

    total = len(recipients)
    render_failures = 0
    dedup_groups = defaultdict(list)

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
            mail = render_template_to_mail(
                template,
                user=None,
                event=event,
                locale=locale,
                context_kwargs=context,
                commit=False,
                allow_empty_address=True,
            )
            dedup_groups[(user, mail.subject, mail.text)].append((mail, context))
        except SendMailException:
            render_failures += 1

        if progress:
            progress(i + 1, total)

    result = []
    with transaction.atomic():
        for (user, _, _), entries in dedup_groups.items():
            mail = entries[0][0]
            mail.save()
            mail.to_users.add(user)
            for _, context in entries:
                if submission := context.get("submission"):
                    mail.submissions.add(submission)
            result.append(mail)

    if skip_queue:
        for mail in result:
            try:
                send_queued_mail(mail)
            except Exception:
                logger.exception("Failed to send mail %d", mail.pk)

    return {
        "count": len(result),
        "render_failures": render_failures,
        "skip_queue": skip_queue,
    }


def send_outbox_mails(*, event, mail_pks, requestor=None, progress=None):
    """Send each DRAFT mail in ``mail_pks``. Non-DRAFT mails are silently
    skipped. ``progress`` is an optional ``(current, total)`` callback.
    """
    mails = list(
        event.queued_mails.filter(pk__in=mail_pks, state=QueuedMailStates.DRAFT)
    )
    total = len(mails)

    for i, mail in enumerate(mails):
        try:
            send_queued_mail(mail, requestor=requestor)
        except Exception:
            logger.exception("Failed to send mail %d", mail.pk)
        if progress:
            progress(i + 1, total)

    return {"count": total}


def expire_stale_queued_mails():
    """Reset mails stuck in SENDING state for over an hour back to DRAFT,
    annotated with a timeout error. Returns the number of mails reset.
    """
    with scopes_disabled():
        cutoff = now() - dt.timedelta(hours=1)
        return QueuedMail.objects.filter(
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
