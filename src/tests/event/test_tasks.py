# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.core import mail as djmail
from django.utils.timezone import now

from pretalx.event.tasks import task_periodic_event_services
from tests.factories import EventFactory
from tests.utils import refresh

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_task_periodic_event_services_nonexistent_slug():
    task_periodic_event_services("nonexistent-event-slug")


def test_task_periodic_event_services_delegates_to_domain():
    """The task is a thin wrapper: load the event by slug, then delegate."""
    djmail.outbox = []
    event = EventFactory(cfp__deadline=now() - dt.timedelta(hours=1))

    task_periodic_event_services(event.slug)

    event = refresh(event)
    assert len(djmail.outbox) == 1
    assert event.settings.sent_mail_cfp_closed
