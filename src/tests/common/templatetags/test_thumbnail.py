import pytest

from pretalx.common.templatetags.thumbnail import thumbnail

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("value", (None, "not-a-field"))
def test_thumbnail_returns_none_for_invalid_input(value):
    """Invalid inputs (None, plain string) have no .url fallback, so None is returned."""
    assert thumbnail(value, "default") is None
