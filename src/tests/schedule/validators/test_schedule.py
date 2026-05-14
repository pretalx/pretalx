# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.schedule.validators.schedule import validate_unique_version
from tests.factories import EventFactory, ScheduleFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_validate_unique_version_accepts_unique_version():
    event = EventFactory()
    ScheduleFactory(event=event, version="v1")

    validate_unique_version("v2", event=event)


def test_validate_unique_version_rejects_duplicate():
    event = EventFactory()
    ScheduleFactory(event=event, version="v1")

    with pytest.raises(ValidationError):
        validate_unique_version("v1", event=event)


def test_validate_unique_version_rejects_duplicate_case_insensitive():
    event = EventFactory()
    ScheduleFactory(event=event, version="V1")

    with pytest.raises(ValidationError):
        validate_unique_version("v1", event=event)


def test_validate_unique_version_allows_self_on_update():
    event = EventFactory()
    schedule = ScheduleFactory(event=event, version="v1")

    validate_unique_version("v1", event=event, exclude_schedule=schedule)


def test_validate_unique_version_skips_when_version_or_event_missing():
    event = EventFactory()

    validate_unique_version(None, event=event)
    validate_unique_version("v1", event=None)
