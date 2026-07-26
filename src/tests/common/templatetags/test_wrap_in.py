# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.utils.safestring import SafeString

from pretalx.common.templatetags.wrap_in import wrap_in

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("content", "expected"),
    (
        ("example.org", "<strong>example.org</strong>"),
        (
            '<script>alert("x")</script>',
            "<strong>&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;</strong>",
        ),
    ),
    ids=("plain_content", "escaped_content"),
)
def test_wrap_in_wraps_escaped_content_in_tag(content, expected):
    result = wrap_in(content, "strong")

    assert result == expected
    assert isinstance(result, SafeString)
