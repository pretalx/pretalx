# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from pretalx.common.templatetags.datetimerange import (
    datetimerange,
    render_time,
    timerange,
    timezone_name,
)

pytestmark = pytest.mark.unit


START = dt.datetime(2024, 6, 15, 10, 0, tzinfo=dt.UTC)


def _time(value, text):
    return (
        f'<time datetime="{value}" data-timezone="UTC" '
        f'data-isodatetime="{value.replace(" ", "T")}:00+00:00" '
        f'aria-description="UTC">{text}</time>'
    )


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    (
        (None, None, ""),
        (START, None, _time("2024-06-15 10:00", "2024-06-15 10:00")),
        (
            START,
            dt.datetime(2024, 6, 15, 12, 0, tzinfo=dt.UTC),
            '<span class="timerange-block">2024-06-15 '
            + _time("2024-06-15 10:00", "10:00")
            + "–"
            + _time("2024-06-15 12:00", "12:00")
            + "</span>",
        ),
        (
            START,
            dt.datetime(2024, 6, 16, 12, 0, tzinfo=dt.UTC),
            '<span class="timerange-block">'
            + _time("2024-06-15 10:00", "2024-06-15 10:00")
            + " – "
            + _time("2024-06-16 12:00", "2024-06-16 12:00")
            + "</span>",
        ),
    ),
    ids=("both_none", "start_only", "same_day", "different_days"),
)
def test_datetimerange(start, end, expected):
    assert str(datetimerange(start, end)) == expected


def test_timerange_same_day_omits_date():
    start = dt.datetime(2024, 6, 15, 10, 0, tzinfo=dt.UTC)
    end = dt.datetime(2024, 6, 15, 12, 0, tzinfo=dt.UTC)

    result = str(timerange(start, end))

    assert result == (
        '<span class="timerange-block">'
        '<time datetime="2024-06-15 10:00" data-timezone="UTC" '
        'data-isodatetime="2024-06-15T10:00:00+00:00" aria-description="UTC">10:00</time>'
        "–"
        '<time datetime="2024-06-15 12:00" data-timezone="UTC" '
        'data-isodatetime="2024-06-15T12:00:00+00:00" aria-description="UTC">12:00</time>'
        "</span>"
    )


@pytest.mark.parametrize(
    "end",
    (dt.datetime(2024, 6, 16, 12, 0, tzinfo=dt.UTC), None),
    ids=["different_days", "no_end"],
)
def test_timerange_falls_back_to_datetimerange(end):
    start = dt.datetime(2024, 6, 15, 10, 0, tzinfo=dt.UTC)

    assert str(timerange(start, end)) == str(datetimerange(start, end))


@pytest.mark.parametrize(
    ("tz", "expected"),
    (
        (
            "UTC",
            (
                '<time datetime="2024-06-15 10:30" data-timezone="UTC" '
                'data-isodatetime="2024-06-15T10:30:00+00:00" '
                'aria-description="UTC">10:30</time>'
            ),
        ),
        (
            "America/New_York",
            (
                '<time datetime="2024-06-15 10:30" data-timezone="America/New_York" '
                'data-isodatetime="2024-06-15T10:30:00-04:00" '
                'aria-description="America/New York">10:30</time>'
            ),
        ),
    ),
)
def test_render_time_produces_time_tag_with_raw_and_readable_timezone(tz, expected):
    time = dt.datetime(2024, 6, 15, 10, 30, tzinfo=ZoneInfo(tz))

    with timezone.override(ZoneInfo(tz)):
        result = str(render_time(time, "TIME_FORMAT"))

    assert result == expected


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
