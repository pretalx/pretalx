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
    if scores:
        sub = SubmissionFactory()
        for score in scores:
            ReviewFactory(submission=sub, score=score)

    result = Review.objects.aggregate(median_score=Median("score"))

    assert result["median_score"] == expected


@pytest.mark.parametrize(
    ("vendor", "fragments", "locale_marker"),
    (
        ("sqlite", ("json_valid", "json_extract", "json_each"), "$.{locale}"),
        (
            "postgresql",
            ("IS JSON OBJECT", "::json->>", "json_each_text"),
            ">>'{locale}'",
        ),
    ),
)
def test_translate_base_template_uses_vendor_json_access(
    vendor, fragments, locale_marker
):
    template = Translate._BASE_TEMPLATES[vendor]

    for fragment in fragments:
        assert fragment in template
    assert locale_marker.format(locale="fr") in template.format(locale="fr")


def _make_translate_lhs():
    field = Submission._meta.get_field("title")
    return field.get_col(Submission._meta.db_table)


def test_translate_transform_template_injects_current_locale():
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
