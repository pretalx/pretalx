import pytest

from pretalx.common.text.xml import strip_control_characters, xmlescape

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("hello", "hello"),
        ("line\ttab", "line\ttab"),  # tab (0x09) is preserved
        ("line\nnewline", "line\nnewline"),  # newline (0x0A) is preserved
        ("with\x00null", "withnull"),  # NUL stripped
        ("bell\x07here", "bellhere"),  # BEL stripped
        ("\x01\x02\x03\x04", ""),  # SOH, STX, ETX, EOT all stripped
        ("\x0bvertical", "vertical"),  # VT stripped
        ("\x1funit_sep", "unit_sep"),  # US stripped
        ("", ""),
        (None, ""),
    ),
)
def test_strip_control_characters(text, expected):
    assert strip_control_characters(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("hello", "hello"),
        ("<tag>", "&lt;tag&gt;"),
        ("a & b", "a &amp; b"),
        ('say "hi"', "say &quot;hi&quot;"),
        ("it's", "it&apos;s"),
        ("\x00hidden", "hidden"),  # control chars stripped
        ("über", "&#252;ber"),  # non-ASCII → XML numeric char ref
        ("日本語", "&#26085;&#26412;&#35486;"),
        ("", ""),
    ),
)
def test_xmlescape(text, expected):
    assert xmlescape(text) == expected


def test_xmlescape_combined():
    """All escaping steps work together on a single input."""
    result = xmlescape("<b class=\"x\">'ñ'\x01</b>")

    assert result == "&lt;b class=&quot;x&quot;&gt;&apos;&#241;&apos;&lt;/b&gt;"
