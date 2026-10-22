# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.template import Context, Template

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("content", "expected"),
    (
        ("Login", "Login :: "),
        ("\n    Login\n    ", "Login :: "),
        ("", ""),
        ("\n    ", ""),
        ("{{ name }}", "Tom &amp; Jerry :: "),
        ("Halfnarp ::\n", "Halfnarp :: "),
    ),
    ids=(
        "plain",
        "surrounding_whitespace",
        "empty",
        "whitespace_only",
        "escaped",
        "legacy_trailing_separator",
    ),
)
def test_title_segment_appends_separator_to_non_empty_content(content, expected):
    template = Template(
        "{% load page_title %}{% filter title_segment %}" + content + "{% endfilter %}"
    )

    assert template.render(Context({"name": "Tom & Jerry"})) == expected
