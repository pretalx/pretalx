# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

from django.db.models import Q
from django.utils.timezone import now

from pretalx.event.domain.mail import send_orga_mail
from pretalx.mail.template_phrases import CFP_CLOSED_TEXT, EVENT_OVER_TEXT


def lifecycle_windows():
    _now = now()
    today = _now.date()
    return (
        (_now - dt.timedelta(days=1), _now),
        (today - dt.timedelta(days=3), today - dt.timedelta(days=1)),
    )


def events_pending_lifecycle_notifications(events):
    deadline_range, date_to_range = lifecycle_windows()
    return events.filter(
        Q(cfp__deadline__range=deadline_range) | Q(date_to__range=date_to_range)
    )


def send_lifecycle_notifications(event):
    """Send the orga the once-off "CfP closed" and "event is over" mails when
    the event reaches those points in its lifecycle.

    Each notification is gated by a ``settings.sent_mail_*`` flag so the mail
    fires exactly once per event. The caller is responsible for entering the
    event scope.
    """
    deadline_range, date_to_range = lifecycle_windows()
    if (
        not event.settings.sent_mail_cfp_closed
        and event.cfp.deadline
        and deadline_range[0] <= event.cfp.deadline <= deadline_range[1]
    ):
        send_orga_mail(event, CFP_CLOSED_TEXT)
        event.settings.sent_mail_cfp_closed = True

    if (
        not event.settings.sent_mail_event_over
        and date_to_range[0] <= event.date_to <= date_to_range[1]
        and event.current_schedule
        and event.current_schedule.talks.filter(is_visible=True).count()
    ):
        send_orga_mail(event, EVENT_OVER_TEXT, stats=True)
        event.settings.sent_mail_event_over = True
