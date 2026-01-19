# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

import pytest
from django.core import mail as djmail
from django.utils.timezone import now

from pretalx.common.models.log import ActivityLog
from pretalx.event.services import (
    task_periodic_event_services,
)


@pytest.mark.django_db
def test_task_periodic_cfp_closed(event):
    djmail.outbox = []
    ActivityLog.objects.create(event=event, content_object=event, action_type="test")
    event.cfp.deadline = now() - dt.timedelta(hours=1)
    event.cfp.save()
    assert not event.settings.sent_mail_cfp_closed
    task_periodic_event_services(event.slug)
    event = event.__class__.objects.get(slug=event.slug)
    assert len(djmail.outbox) == 2  # event created + deadline passed
    assert event.settings.sent_mail_cfp_closed
    task_periodic_event_services(event.slug)
    event = event.__class__.objects.get(slug=event.slug)
    assert len(djmail.outbox) == 2


@pytest.mark.django_db
def test_task_periodic_event_over(event, slot):
    djmail.outbox = []
    ActivityLog.objects.create(event=event, content_object=event, action_type="test")
    event.date_to = now() - dt.timedelta(days=1)
    event.save()
    assert not event.settings.sent_mail_cfp_closed
    task_periodic_event_services(event.slug)
    event = event.__class__.objects.get(slug=event.slug)
    assert len(djmail.outbox) == 2  # event created + event over
    assert event.settings.sent_mail_event_over
    task_periodic_event_services(event.slug)
    event = event.__class__.objects.get(slug=event.slug)
    assert len(djmail.outbox) == 2


@pytest.mark.django_db
def test_task_periodic_event_over_no_talks(event):
    djmail.outbox = []
    ActivityLog.objects.create(event=event, content_object=event, action_type="test")
    event.date_to = now() - dt.timedelta(days=1)
    event.save()
    assert not event.settings.sent_mail_cfp_closed
    task_periodic_event_services(event.slug)
    event = event.__class__.objects.get(slug=event.slug)
    assert len(djmail.outbox) == 1  # event created
    assert not event.settings.sent_mail_event_over
    task_periodic_event_services(event.slug)
    event = event.__class__.objects.get(slug=event.slug)
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_periodic_event_fail():
    task_periodic_event_services("lololol")
