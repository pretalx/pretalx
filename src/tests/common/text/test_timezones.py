# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import zoneinfo

import pytest

from pretalx.common.text.timezones import timezone_name


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("America/New_York", "America/New York"),
        ("Asia/Manila", "Asia/Manila"),
        ("America/Argentina/Buenos_Aires", "America/Argentina/Buenos Aires"),
        ("UTC", "UTC"),
    ),
)
def test_timezone_name_humanises_underscores(value, expected):
    assert timezone_name(value) == expected


def test_timezone_name_accepts_tzinfo_objects():
    assert timezone_name(zoneinfo.ZoneInfo("America/New_York")) == "America/New York"
