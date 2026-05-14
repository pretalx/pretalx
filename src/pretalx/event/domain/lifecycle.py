# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

from django.utils.timezone import now

from pretalx.event.domain.mail import send_orga_mail
from pretalx.mail.template_phrases import CFP_CLOSED_TEXT, EVENT_OVER_TEXT


def send_lifecycle_notifications(event):
    """Send the orga the once-off "CfP closed" and "event is over" mails when
    the event reaches those points in its lifecycle.

    Each notification is gated by a ``settings.sent_mail_*`` flag so the mail
    fires exactly once per event. The caller is responsible for entering the
    event scope.
    """
    _now = now()
    if (
        not event.settings.sent_mail_cfp_closed
        and event.cfp.deadline
        and dt.timedelta(0) <= (_now - event.cfp.deadline) <= dt.timedelta(days=1)
    ):
        send_orga_mail(event, CFP_CLOSED_TEXT)
        event.settings.sent_mail_cfp_closed = True

    if (
        not event.settings.sent_mail_event_over
        and (
            (_now.date() - dt.timedelta(days=3))
            <= event.date_to
            <= (_now.date() - dt.timedelta(days=1))
        )
        and event.current_schedule
        and event.current_schedule.talks.filter(is_visible=True).count()
    ):
        send_orga_mail(event, EVENT_OVER_TEXT, stats=True)
        event.settings.sent_mail_event_over = True
