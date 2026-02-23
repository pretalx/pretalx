# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

import pytest
from django.core import mail as djmail
from django.utils.timezone import now
from django_scopes import scope

from pretalx.common.models.file import CachedFile
from pretalx.common.models.log import ActivityLog
from pretalx.event.services import clean_cached_files, task_periodic_event_services


@pytest.mark.django_db
def test_task_periodic_cfp_closed(event):
    djmail.outbox = []
    ActivityLog.objects.create(event=event, content_object=event, action_type="test")
    with scope(event=event):
        event.cfp.deadline = now() - dt.timedelta(hours=1)
        event.cfp.save()
    assert not event.settings.sent_mail_cfp_closed
    task_periodic_event_services(event.slug)
    event = event.__class__.objects.get(slug=event.slug)
    assert len(djmail.outbox) == 1  # deadline passed
    assert event.settings.sent_mail_cfp_closed
    task_periodic_event_services(event.slug)
    event = event.__class__.objects.get(slug=event.slug)
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_task_periodic_event_over(event, slot):
    djmail.outbox = []
    ActivityLog.objects.create(event=event, content_object=event, action_type="test")
    event.date_to = now() - dt.timedelta(days=1)
    event.save()
    assert not event.settings.sent_mail_cfp_closed
    task_periodic_event_services(event.slug)
    event = event.__class__.objects.get(slug=event.slug)
    assert len(djmail.outbox) == 1  # event over
    assert event.settings.sent_mail_event_over
    task_periodic_event_services(event.slug)
    event = event.__class__.objects.get(slug=event.slug)
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
def test_task_periodic_event_over_no_talks(event):
    djmail.outbox = []
    ActivityLog.objects.create(event=event, content_object=event, action_type="test")
    event.date_to = now() - dt.timedelta(days=1)
    event.save()
    assert not event.settings.sent_mail_cfp_closed
    task_periodic_event_services(event.slug)
    event = event.__class__.objects.get(slug=event.slug)
    assert len(djmail.outbox) == 0
    assert not event.settings.sent_mail_event_over
    task_periodic_event_services(event.slug)
    event = event.__class__.objects.get(slug=event.slug)
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
def test_periodic_event_fail():
    task_periodic_event_services("lololol")


@pytest.mark.django_db
def test_cleanup_expired_cached_files():
    expired = CachedFile.objects.create(
        expires=now() - dt.timedelta(hours=1),
        filename="expired.zip",
        content_type="application/zip",
    )
    not_expired = CachedFile.objects.create(
        expires=now() + dt.timedelta(hours=1),
        filename="not_expired.zip",
        content_type="application/zip",
    )

    clean_cached_files(sender=None)

    assert not CachedFile.objects.filter(pk=expired.pk).exists()
    assert CachedFile.objects.filter(pk=not_expired.pk).exists()
