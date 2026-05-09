# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.core import mail as djmail
from django.utils.timezone import now

from pretalx.event.domain.lifecycle import send_lifecycle_notifications
from tests.factories import (
    EventFactory,
    ScheduleFactory,
    SubmissionFactory,
    TalkSlotFactory,
)
from tests.utils import refresh

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

ORGA_MAIL_SUBJECT = "News from your content system"


def test_send_lifecycle_notifications_sends_cfp_closed_mail():
    djmail.outbox = []
    event = EventFactory(cfp__deadline=now() - dt.timedelta(hours=1))

    assert not event.settings.sent_mail_cfp_closed

    send_lifecycle_notifications(event)

    event = refresh(event)
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [event.email]
    assert djmail.outbox[0].subject == ORGA_MAIL_SUBJECT
    assert event.settings.sent_mail_cfp_closed


def test_send_lifecycle_notifications_cfp_closed_mail_sent_only_once():
    djmail.outbox = []
    event = EventFactory(cfp__deadline=now() - dt.timedelta(hours=1))

    send_lifecycle_notifications(event)
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [event.email]
    assert djmail.outbox[0].subject == ORGA_MAIL_SUBJECT

    send_lifecycle_notifications(event)
    assert len(djmail.outbox) == 1


def test_send_lifecycle_notifications_no_cfp_closed_mail_before_deadline():
    djmail.outbox = []
    event = EventFactory(cfp__deadline=now() + dt.timedelta(days=1))

    send_lifecycle_notifications(event)

    assert len(djmail.outbox) == 0
    event = refresh(event)
    assert not event.settings.sent_mail_cfp_closed


def test_send_lifecycle_notifications_no_cfp_closed_mail_after_one_day():
    djmail.outbox = []
    event = EventFactory(cfp__deadline=now() - dt.timedelta(days=2))

    send_lifecycle_notifications(event)

    assert len(djmail.outbox) == 0
    event = refresh(event)
    assert not event.settings.sent_mail_cfp_closed


def test_send_lifecycle_notifications_sends_event_over_mail():
    djmail.outbox = []
    event = EventFactory(
        date_from=(now() - dt.timedelta(days=3)).date(),
        date_to=(now() - dt.timedelta(days=1)).date(),
    )
    submission = SubmissionFactory(event=event)
    schedule = ScheduleFactory(
        event=event, version="v1", published=now() - dt.timedelta(days=5)
    )
    TalkSlotFactory(submission=submission, schedule=schedule)

    send_lifecycle_notifications(event)

    event = refresh(event)
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [event.email]
    assert djmail.outbox[0].subject == ORGA_MAIL_SUBJECT
    assert event.settings.sent_mail_event_over


def test_send_lifecycle_notifications_event_over_mail_sent_only_once():
    djmail.outbox = []
    event = EventFactory(
        date_from=(now() - dt.timedelta(days=3)).date(),
        date_to=(now() - dt.timedelta(days=1)).date(),
    )
    submission = SubmissionFactory(event=event)
    schedule = ScheduleFactory(
        event=event, version="v1", published=now() - dt.timedelta(days=5)
    )
    TalkSlotFactory(submission=submission, schedule=schedule)

    send_lifecycle_notifications(event)
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [event.email]
    assert djmail.outbox[0].subject == ORGA_MAIL_SUBJECT

    send_lifecycle_notifications(event)
    assert len(djmail.outbox) == 1


def test_send_lifecycle_notifications_no_event_over_mail_without_visible_talks():
    djmail.outbox = []
    event = EventFactory(
        date_from=(now() - dt.timedelta(days=3)).date(),
        date_to=(now() - dt.timedelta(days=1)).date(),
    )

    send_lifecycle_notifications(event)

    assert len(djmail.outbox) == 0
    event = refresh(event)
    assert not event.settings.sent_mail_event_over


def test_send_lifecycle_notifications_no_event_over_mail_when_event_too_old():
    djmail.outbox = []
    event = EventFactory(
        date_from=(now() - dt.timedelta(days=10)).date(),
        date_to=(now() - dt.timedelta(days=5)).date(),
    )
    submission = SubmissionFactory(event=event)
    schedule = ScheduleFactory(
        event=event, version="v1", published=now() - dt.timedelta(days=10)
    )
    TalkSlotFactory(submission=submission, schedule=schedule)

    send_lifecycle_notifications(event)

    assert len(djmail.outbox) == 0
    event = refresh(event)
    assert not event.settings.sent_mail_event_over
