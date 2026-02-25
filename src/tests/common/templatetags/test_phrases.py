import pytest

from pretalx.common.templatetags.phrases import phrase

pytestmark = pytest.mark.unit


def test_phrase_without_kwargs():
    result = phrase("phrases.base.save")
    assert str(result) == "Save"


def test_phrase_with_kwargs():
    """Phrase with %-formatting substitutes kwargs."""
    result = phrase("phrases.schedule.timezone_hint", tz="Europe/Berlin")
    assert "Europe/Berlin" in str(result)
