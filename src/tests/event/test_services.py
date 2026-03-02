# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.core import mail as djmail
from django.utils.timezone import now
from django_scopes import scope

from pretalx.common.models.file import CachedFile
from pretalx.event.services import (
    clean_cached_files,
    periodic_event_services,
    task_periodic_event_services,
)
from tests.factories import (
    CachedFileFactory,
    EventFactory,
    ReviewPhaseFactory,
    ScheduleFactory,
    SubmissionFactory,
    TalkSlotFactory,
)
from tests.utils import refresh

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

ORGA_MAIL_SUBJECT = "News from your content system"


def test_task_periodic_event_services_nonexistent_slug():
    task_periodic_event_services("nonexistent-event-slug")


def test_task_periodic_event_services_sends_cfp_closed_mail():
    djmail.outbox = []
    event = EventFactory(cfp__deadline=now() - dt.timedelta(hours=1))

    assert not event.settings.sent_mail_cfp_closed

    task_periodic_event_services(event.slug)

    event = refresh(event)
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [event.email]
    assert djmail.outbox[0].subject == ORGA_MAIL_SUBJECT
    assert event.settings.sent_mail_cfp_closed


def test_task_periodic_event_services_cfp_closed_mail_sent_only_once():
    djmail.outbox = []
    event = EventFactory(cfp__deadline=now() - dt.timedelta(hours=1))

    task_periodic_event_services(event.slug)
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [event.email]
    assert djmail.outbox[0].subject == ORGA_MAIL_SUBJECT

    task_periodic_event_services(event.slug)
    assert len(djmail.outbox) == 1


def test_task_periodic_event_services_no_cfp_closed_mail_before_deadline():
    djmail.outbox = []
    event = EventFactory(cfp__deadline=now() + dt.timedelta(days=1))

    task_periodic_event_services(event.slug)

    assert len(djmail.outbox) == 0
    event = refresh(event)
    assert not event.settings.sent_mail_cfp_closed


def test_task_periodic_event_services_no_cfp_closed_mail_after_one_day():
    djmail.outbox = []
    event = EventFactory(cfp__deadline=now() - dt.timedelta(days=2))

    task_periodic_event_services(event.slug)

    assert len(djmail.outbox) == 0
    event = refresh(event)
    assert not event.settings.sent_mail_cfp_closed


def test_task_periodic_event_services_sends_event_over_mail():
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

    task_periodic_event_services(event.slug)

    event = refresh(event)
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [event.email]
    assert djmail.outbox[0].subject == ORGA_MAIL_SUBJECT
    assert event.settings.sent_mail_event_over


def test_task_periodic_event_services_event_over_mail_sent_only_once():
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

    task_periodic_event_services(event.slug)
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == [event.email]
    assert djmail.outbox[0].subject == ORGA_MAIL_SUBJECT

    task_periodic_event_services(event.slug)
    assert len(djmail.outbox) == 1


def test_task_periodic_event_services_no_event_over_mail_without_visible_talks():
    djmail.outbox = []
    event = EventFactory(
        date_from=(now() - dt.timedelta(days=3)).date(),
        date_to=(now() - dt.timedelta(days=1)).date(),
    )

    task_periodic_event_services(event.slug)

    assert len(djmail.outbox) == 0
    event = refresh(event)
    assert not event.settings.sent_mail_event_over


def test_task_periodic_event_services_no_event_over_mail_when_event_too_old():
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

    task_periodic_event_services(event.slug)

    assert len(djmail.outbox) == 0
    event = refresh(event)
    assert not event.settings.sent_mail_event_over


def test_periodic_event_services_updates_review_phases(event):
    """periodic_event_services runs the periodic task (eagerly) and
    updates review phases, deactivating an expired one."""
    with scope(event=event):
        event.review_phases.all().delete()
        expired_phase = ReviewPhaseFactory(
            event=event,
            name="Expired",
            start=now() - dt.timedelta(days=10),
            end=now() - dt.timedelta(days=3),
            is_active=True,
            position=0,
        )

    periodic_event_services(sender=None)

    expired_phase.refresh_from_db()
    assert not expired_phase.is_active


def test_periodic_event_services_skips_old_events():
    djmail.outbox = []
    EventFactory(
        date_from=(now() - dt.timedelta(days=10)).date(),
        date_to=(now() - dt.timedelta(days=5)).date(),
        cfp__deadline=now() - dt.timedelta(hours=1),
    )

    periodic_event_services(sender=None)

    assert len(djmail.outbox) == 0


def test_clean_cached_files_deletes_only_expired():
    expired = CachedFileFactory(expires=now() - dt.timedelta(hours=1))
    not_expired = CachedFileFactory(expires=now() + dt.timedelta(hours=1))

    clean_cached_files(sender=None)

    assert not CachedFile.objects.filter(pk=expired.pk).exists()
    assert CachedFile.objects.filter(pk=not_expired.pk).exists()
