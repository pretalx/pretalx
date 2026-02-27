import pytest
from django.conf import settings
from django.utils import translation

from pretalx.orga.utils.i18n import (
    Translate,
    get_javascript_format,
    get_moment_locale,
    has_i18n_content,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("locale", "expected"),
    (
        ("af", "af"),
        ("hy-am", "hy-am"),
        ("de-DE", "de"),
        ("de_DE", "de"),
        ("ja_JP", "ja"),
        ("delol_DE", settings.LANGUAGE_CODE),
    ),
)
def test_get_moment_locale_with_explicit_locale(locale, expected):
    assert get_moment_locale(locale) == expected


def test_get_moment_locale_falls_back_to_active_language():
    """Without an explicit locale, get_moment_locale uses the active language."""
    with translation.override("de"):
        assert get_moment_locale() == "de"


def test_get_moment_locale_fallback_for_unknown_language():
    with translation.override("xx"):
        assert get_moment_locale() == settings.LANGUAGE_CODE


def test_get_javascript_format_converts_date_format():
    """get_javascript_format converts Python strftime tokens to moment.js tokens."""
    with translation.override("en"):
        result = get_javascript_format("DATE_INPUT_FORMATS")
        assert "%" not in result
        assert any(token in result for token in ("YYYY", "MM", "DD", "YY", "hh", "HH"))


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (None, False),
        ("", False),
        (0, False),
        ({}, False),
        ("hello", True),
        ("  ", False),
        ({"en": "hello"}, True),
        ({"en": "", "de": ""}, False),
        ({"en": "  ", "de": ""}, False),
        ({"en": "", "de": "Hallo"}, True),
        ({"en": None, "de": "Hallo"}, True),
    ),
)
def test_has_i18n_content(value, expected):
    assert has_i18n_content(value) is expected


def test_translate_base_template_sqlite_uses_json_extract():
    template = Translate._BASE_TEMPLATES["sqlite"]
    assert "json_valid" in template
    assert "json_extract" in template
    assert "json_each" in template


def test_translate_base_template_postgresql_uses_json_operators():
    template = Translate._BASE_TEMPLATES["postgresql"]
    assert "IS JSON OBJECT" in template
    assert "::json->>" in template
    assert "json_each_text" in template


@pytest.mark.parametrize("locale", ("fr", "de"))
def test_translate_base_template_sqlite_injects_locale(locale):
    rendered = Translate._BASE_TEMPLATES["sqlite"].format(locale=locale)
    assert f"$.{locale}" in rendered


@pytest.mark.parametrize("locale", ("fr", "de"))
def test_translate_base_template_postgresql_injects_locale(locale):
    rendered = Translate._BASE_TEMPLATES["postgresql"].format(locale=locale)
    assert f">>'{locale}'" in rendered


def _make_translate_lhs():
    """Build a valid lhs expression for the Translate transform using a real model field."""
    from pretalx.submission.models import Submission  # noqa: PLC0415

    field = Submission._meta.get_field("title")
    return field.get_col(Submission._meta.db_table)


@pytest.mark.django_db
def test_translate_transform_template_injects_current_locale():
    """The template property inserts the active language into the SQL."""
    lhs = _make_translate_lhs()
    transform = Translate(lhs)

    with translation.override("fr"):
        assert "$.fr" in transform.template
    with translation.override("de"):
        assert "$.de" in transform.template


@pytest.mark.django_db
def test_translate_transform_unsupported_vendor_raises():
    from unittest.mock import patch  # noqa: PLC0415

    lhs = _make_translate_lhs()
    with patch("pretalx.orga.utils.i18n.connection") as mock_conn:
        mock_conn.vendor = "mysql"
        with pytest.raises(NotImplementedError, match="mysql"):
            Translate(lhs)
