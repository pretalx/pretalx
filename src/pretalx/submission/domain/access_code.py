# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import transaction
from django.db.models import Count, F
from django.utils.translation import gettext_lazy as _

from pretalx.common.exceptions import SubmissionError
from pretalx.mail.domain.render import build_trusted_mail
from pretalx.mail.domain.send import send_transient
from pretalx.submission.models import SubmitterAccessCode


def can_delete_access_code(access_code) -> bool:
    """True iff ``access_code`` has not been used by any submission."""
    return not access_code.submissions.exists()


@transaction.atomic
def redeem_access_code(access_code):
    # Lock so that concurrent redemptions don't exceed ``maximum_uses``
    locked = (
        SubmitterAccessCode.objects.select_for_update()
        .filter(pk=access_code.pk)
        .first()
    )
    if locked is None or not locked.redemptions_valid:
        raise SubmissionError(_("This access code can no longer be used."))
    SubmitterAccessCode.objects.filter(pk=access_code.pk).update(
        redeemed=F("redeemed") + 1
    )
    access_code.refresh_from_db(fields=["redeemed"])


def delete_orphan_access_codes(queryset, m2m_field):
    """Delete the access codes in ``queryset`` whose only reference via
    ``m2m_field`` is the row that ``queryset`` was scoped through. Used
    from ``Track.delete`` and ``SubmissionType.delete`` to clean up codes
    that would no longer point anywhere.

    The ``pk__in=queryset.values("pk")`` indirection is load-bearing:
    annotating ``Count`` directly on the related manager would reuse the
    M2M join that is already filtered to the parent row, so the count
    would always be 1.
    """
    code_model = queryset.model
    code_model.objects.filter(pk__in=queryset.values("pk")).annotate(
        m2m_count=Count(m2m_field)
    ).filter(m2m_count=1).delete()


def send_access_code(access_code, *, user, recipient, subject, text):
    """Send the access-code invitation mail to the given recipient and
    record the action in the access code's log.

    ``subject`` and ``text`` are organiser-authored and represent the
    final text; there is no placeholder rendering here.
    """
    send_transient(
        build_trusted_mail(
            event=access_code.event, to=recipient, subject=subject, text=text
        )
    )
    access_code.log_action(
        "pretalx.access_code.send", person=user, orga=True, data={"email": recipient}
    )
