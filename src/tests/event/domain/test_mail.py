# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.core import mail as djmail
from django_scopes import scope

from pretalx.event.domain.mail import send_orga_mail
from pretalx.schedule.domain.release import freeze_schedule
from tests.utils import refresh

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_send_orga_mail_delivers_email(event):
    djmail.outbox = []
    text = "Dashboard: {event_dashboard}, Submissions: {submission_count}"

    with scope(event=event):
        send_orga_mail(event, text)

    assert len(djmail.outbox) == 1
    sent = djmail.outbox[0]
    assert sent.to == [event.email]
    assert sent.subject == "News from your content system"
    assert sent.body == (f"Dashboard: {event.orga_urls.base.full()}, Submissions: 0")


def test_send_orga_mail_with_stats(event):
    with scope(event=event):
        wip = event.wip_schedule
    freeze_schedule(wip, name="v1")

    event = refresh(event)
    djmail.outbox = []
    text = (
        "Talks: {talk_count}, Reviews: {review_count}, "
        "Schedules: {schedule_count}, Mails: {mail_count}, "
        "Submissions: {submission_count}"
    )

    with scope(event=event):
        send_orga_mail(event, text, stats=True)

    assert len(djmail.outbox) == 1
    sent = djmail.outbox[0]
    assert sent.to == [event.email]
    assert sent.subject == "News from your content system"
    assert sent.body == "Talks: 0, Reviews: 0, Schedules: 1, Mails: 0, Submissions: 0"


def test_send_orga_mail_uses_event_locale(event):
    """The event locale is forwarded to the renderer; the lazy subject
    resolves to that language without the caller having to wrap the call
    in :func:`override`."""
    event.locale = "de"
    event.locale_array = "en,de"
    event.save()
    djmail.outbox = []

    with scope(event=event):
        send_orga_mail(event, "Body")

    assert djmail.outbox[0].subject == "Nachricht von deinem Beitrags-System"
