# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.utils.translation import gettext_lazy as _

from pretalx.mail.domain.send import send_system_mail
from pretalx.mail.enums import QueuedMailStates


def send_orga_mail(
    event, text, *, stats=False, safe_extra_context=None, **context_kwargs
):
    """Send an organiser-facing notification about ``event``. Uses the
    global mail backend.
    """
    internal_safe_extra = {
        # Internally-built orga URLs. Passing the urlman attributes
        # directly lets get_mail_context() resolve them to absolute,
        # mark_safe-wrapped strings so the HTML formatter does not
        # mangle query-string ``&``.
        "event_dashboard": event.orga_urls.base,
        "event_review": event.orga_urls.reviews,
        "event_schedule": event.orga_urls.schedule,
        "event_submissions": event.orga_urls.submissions,
        "event_team": event.orga_urls.team_settings,
        "submission_count": event.submissions.count(),
    }
    if stats:
        internal_safe_extra.update(
            {
                "talk_count": event.current_schedule.talks.filter(
                    is_visible=True
                ).count(),
                "review_count": event.reviews.count(),
                "schedule_count": event.schedules.count() - 1,
                "mail_count": event.queued_mails.filter(
                    state=QueuedMailStates.SENT
                ).count(),
            }
        )
    if safe_extra_context:
        internal_safe_extra.update(safe_extra_context)
    send_system_mail(
        subject=_("News from your content system"),
        text=text,
        to=event.email,
        event=event,
        locale=event.locale,
        safe_extra_context=internal_safe_extra,
        context_kwargs=context_kwargs,
    )
