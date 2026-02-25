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
    ),
)
def test_daterange_locale_formatting(locale, date_from, date_to, expected):
    with translation.override(locale):
        assert daterange(date_from, date_to) == expected


@pytest.mark.parametrize("locale", ("de", "en", "es"))
def test_daterange_different_years_uses_fallback(locale):
    """When dates span different years, locale-specific formatters return
    empty string and the generic fallback is used."""
    date_from = date(2003, 2, 1)
    date_to = date(2005, 4, 3)

    with translation.override(locale):
        result = daterange(date_from, date_to)

    # The fallback uses DATE_FORMAT, so just verify it contains both years
    assert "2003" in result
    assert "2005" in result


def test_daterange_unknown_locale_uses_fallback():
    """Locales without a dedicated formatter fall back to the generic format."""
    date_from = date(2024, 6, 10)
    date_to = date(2024, 6, 12)

    with translation.override("fr"):
        result = daterange(date_from, date_to)

    assert "2024" in result
