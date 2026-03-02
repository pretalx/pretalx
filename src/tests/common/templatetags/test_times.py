# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.common.templatetags.times import times

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("input_value", "expected"),
    (
        (None, ""),
        (1, "once"),
        (2, "twice"),
        (3, "3 times"),
        (0, "0 times"),
        ("1", "once"),
        ("2", "twice"),
        ("3", "3 times"),
    ),
)
def test_times(input_value, expected):
    assert times(input_value) == expected
