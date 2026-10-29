# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.core.exceptions import ValidationError

from pretalx.schedule.validators.slot import (
    validate_slot_time_range,
    validate_slot_within_event,
)
from tests.factories import EventFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_validate_slot_within_event():
    event = EventFactory()
    day = dt.timedelta(days=1)

    validate_slot_within_event(event.datetime_from + dt.timedelta(hours=1), event=event)
    validate_slot_within_event(None, event=event)
    validate_slot_within_event(event.datetime_from - day, event=None)
    for outside in (event.datetime_from - day, event.datetime_to + day):
        with pytest.raises(ValidationError):
            validate_slot_within_event(outside, event=event)


def test_validate_slot_time_range():
    start = dt.datetime(2024, 1, 1, 10, 0, tzinfo=dt.UTC)
    end = dt.datetime(2024, 1, 1, 11, 0, tzinfo=dt.UTC)

    validate_slot_time_range(start=start, end=end)
    validate_slot_time_range(start=None, end=None)
    validate_slot_time_range(start=start, end=None)
    validate_slot_time_range(start=None, end=end)
    with pytest.raises(ValidationError):
        validate_slot_time_range(start=end, end=start)
