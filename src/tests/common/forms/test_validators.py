# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.core.exceptions import ValidationError
from django.utils.timezone import make_aware

from pretalx.common.forms.validators import (
    MaxDateTimeValidator,
    MaxDateValidator,
    MinDateTimeValidator,
    MinDateValidator,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("validator_class", "limit", "valid_value"),
    (
        (MinDateValidator, dt.date(2024, 1, 1), dt.date(2024, 6, 15)),
        (MaxDateValidator, dt.date(2024, 12, 31), dt.date(2024, 6, 15)),
        (
            MinDateTimeValidator,
            make_aware(dt.datetime(2024, 1, 1, 12, 0)),
            make_aware(dt.datetime(2024, 6, 15, 12, 0)),
        ),
        (
            MaxDateTimeValidator,
            make_aware(dt.datetime(2024, 12, 31, 23, 59)),
            make_aware(dt.datetime(2024, 6, 15, 12, 0)),
        ),
    ),
    ids=["min_date", "max_date", "min_datetime", "max_datetime"],
)
def test_date_validator_accepts_value_within_limit(validator_class, limit, valid_value):
    v = validator_class(limit)

    v(valid_value)


@pytest.mark.parametrize(
    ("validator_class", "limit", "invalid_value"),
    (
        (MinDateValidator, dt.date(2024, 1, 1), dt.date(2023, 12, 31)),
        (MaxDateValidator, dt.date(2024, 12, 31), dt.date(2025, 1, 1)),
        (
            MinDateTimeValidator,
            make_aware(dt.datetime(2024, 1, 1, 12, 0)),
            make_aware(dt.datetime(2023, 12, 31, 12, 0)),
        ),
        (
            MaxDateTimeValidator,
            make_aware(dt.datetime(2024, 12, 31, 23, 59)),
            make_aware(dt.datetime(2025, 1, 1, 0, 0)),
        ),
    ),
    ids=["min_date", "max_date", "min_datetime", "max_datetime"],
)
def test_date_validator_raises_with_formatted_limit(
    validator_class, limit, invalid_value
):
    v = validator_class(limit)

    with pytest.raises(ValidationError) as exc_info:
        v(invalid_value)

    assert "limit_value" in exc_info.value.params
    assert isinstance(exc_info.value.params["limit_value"], str)
