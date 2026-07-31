# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from pretalx.common.templatetags.datetimerange import (
    datetimerange,
    render_time,
    timezone_name,
)

pytestmark = pytest.mark.unit


def test_datetimerange_both_none():
    assert datetimerange(None, None) == ""


def test_datetimerange_start_only():
    start = dt.datetime(2024, 6, 15, 10, 0, tzinfo=dt.UTC)
    result = str(datetimerange(start, None))
    assert "<time" in result
    assert "datetime=" in result
    assert "data-isodatetime=" in result


def test_datetimerange_same_day():
    tz = dt.UTC
    start = dt.datetime(2024, 6, 15, 10, 0, tzinfo=tz)
    end = dt.datetime(2024, 6, 15, 12, 0, tzinfo=tz)
    result = str(datetimerange(start, end))
    assert "timerange-block" in result
    assert "–" in result
    assert result.count("<time") == 2


def test_datetimerange_different_days():
    tz = dt.UTC
    start = dt.datetime(2024, 6, 15, 10, 0, tzinfo=tz)
    end = dt.datetime(2024, 6, 16, 12, 0, tzinfo=tz)
    result = str(datetimerange(start, end))
    assert "timerange-block" in result
    assert " – " in result
    assert result.count("<time") == 2


def test_render_time_produces_time_tag():
    time = dt.datetime(2024, 6, 15, 10, 30, tzinfo=dt.UTC)
    result = str(render_time(time, "TIME_FORMAT"))
    assert result == (
        '<time datetime="2024-06-15 10:30" data-timezone="UTC" '
        'data-isodatetime="2024-06-15T10:30:00+00:00" '
        'aria-description="UTC">10:30</time>'
    )


@pytest.mark.parametrize(
    ("tz", "expected"),
    (
        ("America/New_York", "America/New York"),
        ("America/Argentina/Buenos_Aires", "America/Argentina/Buenos Aires"),
        ("Asia/Manila", "Asia/Manila"),
        ("UTC", "UTC"),
    ),
)
def test_timezone_name_replaces_underscores(tz, expected):
    assert timezone_name(ZoneInfo(tz)) == expected


def test_render_time_keeps_raw_timezone_in_data_attribute():
    time = dt.datetime(2024, 6, 15, 10, 30, tzinfo=ZoneInfo("America/New_York"))

    with timezone.override(ZoneInfo("America/New_York")):
        result = str(render_time(time, "TIME_FORMAT"))

    assert 'data-timezone="America/New_York"' in result
    assert 'aria-description="America/New York"' in result
