# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from datetime import date

import pytest
from django.utils import translation

from pretalx.common.text.daterange import daterange

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("locale", "date_from", "date_to", "expected"),
    (
        # Same day
        ("de", date(2003, 2, 1), date(2003, 2, 1), "1. Februar 2003"),
        ("en", date(2003, 2, 1), date(2003, 2, 1), "Feb. 1, 2003"),
        ("es", date(2003, 2, 1), date(2003, 2, 1), "1 de febrero de 2003"),
        # Same month, different days
        ("de", date(2003, 2, 1), date(2003, 2, 3), "1.–3. Februar 2003"),
        ("en", date(2003, 2, 1), date(2003, 2, 3), "Feb. 1 – 3, 2003"),
        ("es", date(2003, 2, 1), date(2003, 2, 3), "1 - 3 de febrero de 2003"),
        # Same year, different months
        ("de", date(2003, 2, 1), date(2003, 4, 3), "1. Februar – 3. April 2003"),
        ("en", date(2003, 2, 1), date(2003, 4, 3), "Feb. 1 – April 3, 2003"),
        ("es", date(2003, 2, 1), date(2003, 4, 3), "1 de febrero - 3 de abril de 2003"),
        # Different years fall back to DATE_FORMAT
        ("de", date(2003, 2, 1), date(2005, 4, 3), "1. Februar 2003 – 3. April 2005"),
        ("en", date(2003, 2, 1), date(2005, 4, 3), "Feb. 1, 2003 – April 3, 2005"),
        (
            "es",
            date(2003, 2, 1),
            date(2005, 4, 3),
            "1 de febrero de 2003 -3 de abril de 2005",
        ),
        # Unknown locale falls back to DATE_FORMAT
        ("fr", date(2024, 6, 10), date(2024, 6, 12), "10 juin 2024 – 12 juin 2024"),
    ),
)
def test_daterange_locale_formatting(locale, date_from, date_to, expected):
    with translation.override(locale):
        assert daterange(date_from, date_to) == expected
