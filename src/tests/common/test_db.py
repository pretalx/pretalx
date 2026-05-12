# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from unittest.mock import patch

import pytest
from django.db import connection
from django.utils import translation

from pretalx.common.db import Median, Translate
from pretalx.submission.models import Review, Submission
from tests.factories import ReviewFactory, SubmissionFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("scores", "expected"), (([], None), ([4], 4.0), ([3, 7], 5.0))
)
def test_median_aggregate(scores, expected):
    """On SQLite, Median falls back to AVG. Verify it runs and returns the expected value."""
    if scores:
        sub = SubmissionFactory()
        for score in scores:
            ReviewFactory(submission=sub, score=score)

    result = Review.objects.aggregate(median_score=Median("score"))

    assert result["median_score"] == expected


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
    field = Submission._meta.get_field("title")
    return field.get_col(Submission._meta.db_table)


def test_translate_transform_template_injects_current_locale():
    """The template property inserts the active language into the SQL."""
    lhs = _make_translate_lhs()
    transform = Translate(lhs)

    if connection.vendor == "sqlite":  # pragma: no cover -- vendor-specific
        fr_marker, de_marker = "$.fr", "$.de"
    else:  # pragma: no cover -- vendor-specific
        fr_marker, de_marker = ">>'fr'", ">>'de'"

    with translation.override("fr"):
        assert fr_marker in transform.template
    with translation.override("de"):
        assert de_marker in transform.template


def test_translate_transform_unsupported_vendor_raises():
    lhs = _make_translate_lhs()
    with patch("pretalx.common.db.connection") as mock_conn:
        mock_conn.vendor = "mysql"
        with pytest.raises(NotImplementedError, match="mysql"):
            Translate(lhs)
