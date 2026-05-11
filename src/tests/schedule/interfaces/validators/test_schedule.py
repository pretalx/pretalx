# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.schedule.interfaces.validators.schedule import validate_unique_version
from pretalx.schedule.models import Schedule
from tests.factories import EventFactory, ScheduleFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_validate_unique_version_accepts_unique_version():
    event = EventFactory()
    ScheduleFactory(event=event, version="v1")

    validate_unique_version(Schedule(event=event, version="v2"))


def test_validate_unique_version_rejects_duplicate():
    event = EventFactory()
    ScheduleFactory(event=event, version="v1")

    with pytest.raises(ValidationError) as exc_info:
        validate_unique_version(Schedule(event=event, version="v1"))

    assert "version" in exc_info.value.message_dict


def test_validate_unique_version_rejects_duplicate_case_insensitive():
    event = EventFactory()
    ScheduleFactory(event=event, version="V1")

    with pytest.raises(ValidationError) as exc_info:
        validate_unique_version(Schedule(event=event, version="v1"))

    assert "version" in exc_info.value.message_dict


def test_validate_unique_version_allows_self_on_update():
    event = EventFactory()
    schedule = ScheduleFactory(event=event, version="v1")

    validate_unique_version(schedule)


def test_validate_unique_version_skips_when_version_or_event_missing():
    event = EventFactory()

    validate_unique_version(Schedule(event=event, version=None))
    validate_unique_version(Schedule(version="v1"))
