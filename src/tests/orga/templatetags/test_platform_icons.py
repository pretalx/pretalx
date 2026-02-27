import pytest

from pretalx.orga.templatetags.platform_icons import platform_icon
from pretalx.submission.icons import PLATFORM_ICONS

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("icon_name", list(PLATFORM_ICONS.keys()))
def test_platform_icon_returns_svg_for_known_icons(icon_name):
    result = platform_icon(icon_name)
    assert "<svg" in result
    assert hasattr(result, "__html__")


@pytest.mark.parametrize("icon_name", (None, "", "nonexistent"))
def test_platform_icon_returns_empty_for_unknown_icons(icon_name):
    assert platform_icon(icon_name) == ""
