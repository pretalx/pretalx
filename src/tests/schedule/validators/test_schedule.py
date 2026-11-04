# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.schedule.validators.schedule import (
    validate_schedule_version,
    validate_unique_version,
)
from tests.factories import EventFactory, ScheduleFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_validate_unique_version_is_case_insensitive_and_skips_self():
    event = EventFactory()
    schedule = ScheduleFactory(event=event, version="V1")

    validate_unique_version("v2", event=event)
    validate_unique_version("V1", event=event, exclude_schedule=schedule)
    validate_unique_version(None, event=event)
    validate_unique_version("v1", event=None)
    for duplicate in ("V1", "v1"):
        with pytest.raises(ValidationError):
            validate_unique_version(duplicate, event=event)


@pytest.mark.parametrize("version", ("v1.0", "200 km-h", "...", "a.b", "wipe", None))
def test_validate_schedule_version_accepts_valid_version(version):
    validate_schedule_version(version)


@pytest.mark.parametrize(
    ("version", "message"),
    (
        ("200 km/h", "slashes"),
        ("/", "slashes"),
        (".", "slashes"),
        ("..", "slashes"),
        ("WIP", "reserved"),
        (" latest ", "reserved"),
    ),
)
def test_validate_schedule_version_rejects_invalid_version(version, message):
    with pytest.raises(ValidationError, match=message):
        validate_schedule_version(version)
