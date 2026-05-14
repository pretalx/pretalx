# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.core import mail as djmail
from django.utils.timezone import now
from django_scopes import scope

from pretalx.common.models.file import CachedFile
from pretalx.event.receivers import clean_cached_files, periodic_event_services
from tests.factories import CachedFileFactory, EventFactory, ReviewPhaseFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


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
