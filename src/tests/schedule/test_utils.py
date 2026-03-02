# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.schedule.utils import guess_schedule_version
from tests.factories import EventFactory, ScheduleFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("previous_version", "expected"),
    (
        (None, "0.1"),
        ("0.1", "0.2"),
        ("0,2", "0,3"),
        ("0-3", "0-4"),
        ("0_4", "0_5"),
        ("1.0.1", "1.0.2"),
        ("something.1", "something.2"),
        ("Nichtnumerisch", ""),
        ("1.something", ""),
    ),
)
def test_guess_schedule_version(previous_version, expected):
    event = EventFactory()
    if previous_version:
        ScheduleFactory(event=event, version=previous_version)
    assert guess_schedule_version(event) == expected
