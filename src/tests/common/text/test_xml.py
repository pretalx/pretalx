# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from i18nfield.strings import LazyI18nString

from pretalx.common.text.xml import (
    strip_control_characters,
    strip_control_characters_deep,
    xmlescape,
)

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
        ("esc\x1bseq", "escseq"),  # ESC stripped (terminal escape prefix)
        ("del\x7fhere", "delhere"),  # DEL stripped
        ("csi\x9bhere", "csihere"),  # C1 CSI (8-bit escape) stripped
        ("\x80\x90\x9f", ""),  # C1 controls all stripped
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
        ("\x00hidden", "hidden"),  # C0 control stripped
        ("esc\x1bseq", "escseq"),  # ESC stripped before escaping
        ("del\x7fhere", "delhere"),  # DEL stripped, not emitted raw
        ("csi\x9bhere", "csihere"),  # C1 stripped, not emitted as char ref
        ("über", "&#252;ber"),  # non-ASCII → XML numeric char ref
        ("日本語", "&#26085;&#26412;&#35486;"),
        ("", ""),
    ),
)
def test_xmlescape(text, expected):
    assert xmlescape(text) == expected


def test_xmlescape_combined():
    result = xmlescape("<b class=\"x\">'ñ'\x01</b>")

    assert result == "&lt;b class=&quot;x&quot;&gt;&apos;&#241;&apos;&lt;/b&gt;"


def test_strip_control_characters_deep():
    data = {
        "ti\x1btle": "Talk\x1btitle",  # control chars in both key and value
        "rooms": ["Roo\x9bm", "ok"],
        "nested": {"abstract": "a\x00b"},
        # lazy/i18n strings are not str subclasses, but must still be cleaned
        "track": LazyI18nString("Tra\x1bck"),
        "count": 3,  # non-strings are left untouched
        "flag": True,
        "missing": None,
    }

    assert strip_control_characters_deep(data) == {
        "title": "Talktitle",
        "rooms": ["Room", "ok"],
        "nested": {"abstract": "ab"},
        "track": "Track",
        "count": 3,
        "flag": True,
        "missing": None,
    }
