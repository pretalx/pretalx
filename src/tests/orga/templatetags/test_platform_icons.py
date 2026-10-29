# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.orga.templatetags.platform_icons import platform_icon
from pretalx.submission.icons import PLATFORM_ICONS

pytestmark = pytest.mark.unit


def test_platform_icon_returns_svg_for_known_icons():
    for icon_name in PLATFORM_ICONS:
        result = platform_icon(icon_name)
        assert "<svg" in result, icon_name
        assert hasattr(result, "__html__"), icon_name


@pytest.mark.parametrize("icon_name", (None, "", "nonexistent"))
def test_platform_icon_returns_empty_for_unknown_icons(icon_name):
    assert platform_icon(icon_name) == ""
