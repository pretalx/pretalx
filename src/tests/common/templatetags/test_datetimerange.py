# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest

from pretalx.common.templatetags.datetimerange import datetimerange, render_time

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
    """When start and end are on the same day, only the date is shown once
    with time-time range."""
    tz = dt.UTC
    start = dt.datetime(2024, 6, 15, 10, 0, tzinfo=tz)
    end = dt.datetime(2024, 6, 15, 12, 0, tzinfo=tz)
    result = str(datetimerange(start, end))
    assert "timerange-block" in result
    assert "–" in result
    assert result.count("<time") == 2


def test_datetimerange_different_days():
    """When start and end are on different days, both dates are shown."""
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
    assert "<time" in result
    assert "datetime=" in result
    assert "data-isodatetime=" in result
