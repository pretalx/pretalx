# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
import logging
from copy import deepcopy

from django.db import transaction
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.common.exceptions import SendMailException
from pretalx.mail.domain.recipient import Recipient
from pretalx.mail.domain.render import render_template_to_mail
from pretalx.mail.domain.send import send_draft
from pretalx.mail.enums import QueuedMailStates
from pretalx.mail.models import QueuedMail
from pretalx.person.models import SpeakerProfile
from pretalx.schedule.models import TalkSlot
from pretalx.submission.models import Submission

logger = logging.getLogger(__name__)


def save_draft(mail, *, to=None, to_speakers=None, submissions=None, attachments=None):
    """Persist a rendered QueuedMail as a DRAFT row in the outbox.

    Speakers without an effective email are excluded here. If the email
    is meant to be sent immediately, use pretalx.mail.domain.send.send_draft.
    """
    if to_speakers is not None:
        to_speakers = list(to_speakers)
        for speaker in to_speakers:
            if not speaker.effective_email:
                speaker.log_action(
                    "pretalx.mail.skipped",
                    orga=True,
                    data={"subject": str(mail.subject)},
                )
                logger.warning(
                    "Dropping mail recipient %s: no effective email", speaker.code
                )
        to_speakers = [s for s in to_speakers if s.effective_email]
    if to is not None:
        mail.to = to
    if not mail.to and not to_speakers:
        return None
    if attachments is not None:
        mail.attachments = attachments
    mail.save()
    if to_speakers:
        mail.to_speakers.set(to_speakers)
    if submissions:
        mail.submissions.set(submissions)
    return mail


def bulk_create_drafts(template, recipients, *, progress=None):
    """Bulk-render the template over recipient data, collapsing
    identical (speaker, subject, text) tuples and saving unique
    emails as draft.

    Returns (saved_mails, render_failures).
    """
    event = template.event

    speaker_ids = {r["speaker_id"] for r in recipients if "speaker_id" in r}
    speakers_by_id = {
        s.pk: s
        for s in SpeakerProfile.objects.filter(
            pk__in=speaker_ids, event=event
        ).select_related("user", "event")
    }
    user_ids = {r["user_id"] for r in recipients if "speaker_id" not in r}
    speakers_by_user_id = {
        s.user_id: s
        for s in SpeakerProfile.objects.filter(
            user_id__in=user_ids, event=event
        ).select_related("user", "event")
    }

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
        if speaker_id := entry.get("speaker_id"):
            speaker = speakers_by_id.get(speaker_id)
        else:
            speaker = speakers_by_user_id.get(entry["user_id"])
        if speaker is None:
            continue

        context = {"user": Recipient(speaker)}
        if submission_id := entry.get("submission_id"):
            context["submission"] = subs_by_id.get(submission_id)
        if slot_id := entry.get("slot_id"):
            context["slot"] = slots_by_id.get(slot_id)

        locale = speaker.effective_locale
        if submission := context.get("submission"):
            locale = submission.get_email_locale(locale)

        try:
            mail = render_template_to_mail(
                template, locale=locale, context_kwargs=context
            )
        except SendMailException:
            render_failures += 1
            continue

        key = (speaker, mail.subject, mail.text)
        _, submissions = dedup_groups.setdefault(key, (mail, []))
        if submission := context.get("submission"):
            submissions.append(submission)

    saved_mails = []
    with transaction.atomic():
        for (speaker, _, _), (mail, submissions) in dedup_groups.items():
            if save_draft(mail, to_speakers=[speaker], submissions=submissions):
                saved_mails.append(mail)
    return saved_mails, render_failures


def copy_to_draft(mail):
    """Duplicate a sent (or failed) QueuedMail as a fresh DRAFT so an
    organiser can edit and resend it. Recipient M2Ms (to_speakers,
    submissions) are copied; state / sent / error_* fields are reset.
    """
    new_mail = deepcopy(mail)
    new_mail.pk = None
    new_mail._state.adding = True  # force INSERT after deepcopy
    new_mail.sent = None
    new_mail.state = QueuedMailStates.DRAFT
    new_mail.error_data = None
    new_mail.error_timestamp = None
    return save_draft(
        new_mail,
        to_speakers=mail.to_speakers.all(),
        submissions=list(mail.submissions.all()),
    )


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
