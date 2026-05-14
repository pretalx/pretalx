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


def test_validate_slot_within_event_accepts_value_in_range():
    event = EventFactory()

    validate_slot_within_event(event.datetime_from + dt.timedelta(hours=1), event=event)


def test_validate_slot_within_event_rejects_value_before_start():
    event = EventFactory()

    with pytest.raises(ValidationError):
        validate_slot_within_event(
            event.datetime_from - dt.timedelta(days=1), event=event
        )


def test_validate_slot_within_event_rejects_value_after_end():
    event = EventFactory()

    with pytest.raises(ValidationError):
        validate_slot_within_event(
            event.datetime_to + dt.timedelta(days=1), event=event
        )


def test_validate_slot_within_event_skips_when_value_or_event_missing():
    event = EventFactory()

    validate_slot_within_event(None, event=event)
    validate_slot_within_event(event.datetime_from, event=None)


def test_validate_slot_time_range_accepts_start_before_end():
    start = dt.datetime(2024, 1, 1, 10, 0, tzinfo=dt.UTC)
    end = dt.datetime(2024, 1, 1, 11, 0, tzinfo=dt.UTC)

    validate_slot_time_range(start=start, end=end)


def test_validate_slot_time_range_rejects_end_before_start():
    start = dt.datetime(2024, 1, 1, 11, 0, tzinfo=dt.UTC)
    end = dt.datetime(2024, 1, 1, 10, 0, tzinfo=dt.UTC)

    with pytest.raises(ValidationError):
        validate_slot_time_range(start=start, end=end)


def test_validate_slot_time_range_skips_when_missing():
    validate_slot_time_range(start=None, end=None)
    validate_slot_time_range(
        start=dt.datetime(2024, 1, 1, 10, 0, tzinfo=dt.UTC), end=None
    )
    validate_slot_time_range(
        start=None, end=dt.datetime(2024, 1, 1, 10, 0, tzinfo=dt.UTC)
    )
