import pytest

from pretalx.common.templatetags.xmlescape import xmlescape

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("input_text", "expected"),
    (
        ("i am a normal string ??!!$%/()=?", "i am a normal string ??!!$%/()=?"),
        ("<", "&lt;"),
        (">", "&gt;"),
        ('"', "&quot;"),
        ("'", "&apos;"),
        ("&", "&amp;"),
        ("a\aa", "aa"),
        ("ä", "&#228;"),
    ),
)
def test_xmlescape(input_text, expected):
    assert xmlescape(input_text) == expected
