# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
import logging
from copy import deepcopy

from django.db import transaction
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.common.exceptions import SendMailException
from pretalx.mail.domain.render import render_template_to_mail
from pretalx.mail.domain.send import send_draft
from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.models import QueuedMail
from pretalx.person.models import User
from pretalx.schedule.models import TalkSlot
from pretalx.submission.models import Submission

logger = logging.getLogger(__name__)


def save_draft(mail, *, to=None, to_users=None, submissions=None, attachments=None):
    """Persist a rendered :class:`QueuedMail` as a DRAFT row in the
    outbox: write the row, optionally set its ``to`` address, attach its
    M2Ms. ``to`` is a comma-separated string of raw addresses (or a
    single address); ``to_users`` is an iterable of
    :class:`~pretalx.person.models.User`. The two are independent and
    may be combined. ``attachments`` is the JSON-serialisable list stored
    on :attr:`QueuedMail.attachments`.

    Drafts sit in the outbox until an organiser action sends them; for
    immediate delivery, follow this call with
    :func:`~pretalx.mail.domain.send.send_draft`.
    """
    if to is not None:
        mail.to = to
    if attachments is not None:
        mail.attachments = attachments
    mail.save()
    if to_users:
        mail.to_users.set(to_users)
    if submissions:
        mail.submissions.set(submissions)
    return mail


def bulk_create_drafts(template, recipients, *, progress=None):
    """Bulk-render ``template`` over recipient dicts (``{"user_id",
    ["submission_id"], ["slot_id"]}``), collapsing identical
    ``(user, subject, text)`` triples and persisting each unique mail
    as a DRAFT in the outbox with its recipient and submissions
    attached. Recipients whose user is gone or whose render raises
    :class:`SendMailException` are skipped silently. Returns
    ``(saved_mails, render_failures)``.
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
    dedup_groups = {}

    for i, entry in enumerate(recipients):
        if progress:
            progress(i + 1, total)
        if (user := users_by_id.get(entry["user_id"])) is None:
            continue

        context = {"user": user}
        if submission_id := entry.get("submission_id"):
            context["submission"] = subs_by_id.get(submission_id)
        if slot_id := entry.get("slot_id"):
            context["slot"] = slots_by_id.get(slot_id)

        locale = user.locale
        if submission := context.get("submission"):
            locale = submission.get_email_locale(user.locale)

        try:
            mail = render_template_to_mail(
                template, locale=locale, context_kwargs=context
            )
        except SendMailException:
            render_failures += 1
            continue

        key = (user, mail.subject, mail.text)
        _, submissions = dedup_groups.setdefault(key, (mail, []))
        if submission := context.get("submission"):
            submissions.append(submission)

    saved_mails = []
    with transaction.atomic():
        for (user, _, _), (mail, submissions) in dedup_groups.items():
            save_draft(mail, to_users=[user], submissions=submissions)
            saved_mails.append(mail)
    return saved_mails, render_failures


def copy_to_draft(mail):
    """Duplicate a sent (or failed) :class:`QueuedMail` as a fresh DRAFT
    so an organiser can edit and resend it. Recipient M2Ms (``to_users``,
    ``submissions``) are copied; ``state`` / ``sent`` / ``error_*``
    fields are reset.
    """
    new_mail = deepcopy(mail)
    new_mail.pk = None
    new_mail._state.adding = True  # force INSERT after deepcopy
    new_mail.sent = None
    new_mail.state = QueuedMailStates.DRAFT
    new_mail.error_data = None
    new_mail.error_timestamp = None
    new_mail.save()
    new_mail.to_users.set(mail.to_users.all())
    new_mail.submissions.set(mail.submissions.all())
    return new_mail


def send_outbox_mails(*, event, mail_pks, requestor=None, progress=None):
    """Send each DRAFT mail in ``mail_pks``.
    ``progress`` is an optional ``(current, total)`` callback.
    """
    mails = list(
        event.queued_mails.filter(
            pk__in=mail_pks, state=QueuedMailStates.DRAFT
        ).select_related("event")
    )
    total = len(mails)

    for i, mail in enumerate(mails):
        try:
            send_draft(mail, requestor=requestor)
        except Exception:
            logger.exception("Failed to send mail %d", mail.pk)
        if progress:
            progress(i + 1, total)

    return {"count": total}


def expire_stale_queued_mails():
    """Reset mails stuck in SENDING state for over an hour back to DRAFT,
    annotated with a timeout error. Returns the number of mails reset.
    """
    frozen_now = now()
    with scopes_disabled():
        return QueuedMail.objects.filter(
            state=QueuedMailStates.SENDING,
            updated__lt=frozen_now - dt.timedelta(hours=1),
        ).update(
            state=QueuedMailStates.DRAFT,
            error_data={
                "error": "Timed out waiting for delivery confirmation",
                "type": "TimeoutError",
            },
            error_timestamp=frozen_now,
            updated=frozen_now,
        )
