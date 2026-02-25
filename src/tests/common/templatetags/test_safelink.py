import pytest

from pretalx.common.templatetags.safelink import safelink

pytestmark = pytest.mark.unit


def test_safelink_produces_redirect_url():
    result = safelink("https://example.com")
    assert "redirect" in result
    assert "url=" in result
