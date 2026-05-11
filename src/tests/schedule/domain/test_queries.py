# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils.timezone import now

from pretalx.schedule.domain.queries.schedule import published_schedules
from tests.factories import ScheduleFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_published_schedules_excludes_wip(event):
    assert list(published_schedules(event)) == []


def test_published_schedules_includes_only_versioned(event):
    ScheduleFactory(event=event, version="v1")

    result = list(published_schedules(event))

    assert [s.version for s in result] == ["v1"]


def test_published_schedules_orders_newest_first(event):
    ScheduleFactory(event=event, version="v1", published=now() - dt.timedelta(hours=2))
    ScheduleFactory(event=event, version="v2", published=now() - dt.timedelta(hours=1))

    result = list(published_schedules(event))

    assert [s.version for s in result] == ["v2", "v1"]


def test_published_schedules_preloads_event(event, django_assert_num_queries):
    ScheduleFactory(event=event, version="v1")

    result = list(published_schedules(event))

    with django_assert_num_queries(0):
        _ = result[0].event.slug
