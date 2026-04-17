# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from decimal import Decimal

import pytest
from django.core.exceptions import SuspiciousOperation
from django.utils.safestring import SafeString, mark_safe
from i18nfield.strings import LazyI18nString

from pretalx.common.text.formatting import (
    MODE_HTML,
    MODE_PLAIN,
    EmailAlternativeString,
    FormattedString,
    defuse_markdown_links,
    format_map,
)

pytestmark = pytest.mark.unit


def test_plain_mode_passes_strings_verbatim():
    assert format_map("Hi {name}!", {"name": "Jane"}, mode=MODE_PLAIN) == "Hi Jane!"


def test_plain_mode_does_not_escape_html_chars():
    assert format_map("Hi {name}", {"name": "<br>"}, mode=MODE_PLAIN) == "Hi <br>"


def test_html_mode_escapes_angle_brackets_and_ampersand():
    assert format_map("Hi {name}", {"name": "<br>"}, mode=MODE_HTML) == "Hi &lt;br&gt;"
    assert format_map("Hi {name}", {"name": "A & B"}, mode=MODE_HTML) == "Hi A &amp; B"


def test_html_mode_escapes_the_cve_payload():
    payload = (
        "user,<br>We have detected suspicious activity. "
        '<a href="https://phish.com">Click here to secure your account.</a a=">'
    )
    result = format_map(
        "Hi {name},\n\nPlease click foo.", {"name": payload}, mode=MODE_HTML
    )
    assert "<a href=" not in result
    assert "&lt;a href=" in result
    assert "https://phish.com" in result


def test_html_mode_respects_safe_string_from_mark_safe():
    # A SafeString URL must round-trip with ``&`` intact so the
    # downstream markdown linkifier can parse it.
    url = mark_safe("https://foo.test/path?a=1&b=2")
    result = format_map("See {url}", {"url": url}, mode=MODE_HTML)
    assert result == "See https://foo.test/path?a=1&b=2"


def test_email_alternative_dispatches_on_mode():
    alt = EmailAlternativeString("the plain form", "<b>the html form</b>")
    assert (
        format_map("Value: {x}", {"x": alt}, mode=MODE_PLAIN) == "Value: the plain form"
    )
    assert (
        format_map("Value: {x}", {"x": alt}, mode=MODE_HTML)
        == "Value: <b>the html form</b>"
    )


def test_non_string_values_are_coerced():
    assert format_map("Count: {n}", {"n": 42}, mode=MODE_PLAIN) == "Count: 42"
    assert format_map("Count: {n}", {"n": 42}, mode=MODE_HTML) == "Count: 42"
    assert (
        format_map("Total: {n}", {"n": Decimal("19.95")}, mode=MODE_PLAIN)
        == "Total: 19.95"
    )
    assert (
        format_map("Lazy: {msg}", {"msg": LazyI18nString("hello")}, mode=MODE_HTML)
        == "Lazy: hello"
    )


def test_missing_placeholder_raises_by_default():
    # Strict mode so typos in organiser templates fail loudly instead
    # of delivering a literal ``{foo}``.
    with pytest.raises(KeyError):
        format_map("Hi {name}", {}, mode=MODE_PLAIN)


def test_missing_placeholder_is_left_literal_when_tolerated():
    # Tolerant mode for live previews while the organiser types.
    assert (
        format_map("Hi {name}", {}, mode=MODE_PLAIN, raise_on_missing=False)
        == "Hi {name}"
    )


def test_attribute_access_is_blocked():
    # Attribute access would be a format-string abuse vector; the
    # formatter treats ``obj.password`` as a literal composite key.
    class Thing:
        password = "hunter2"

    with pytest.raises(KeyError):
        format_map("{obj.password}", {"obj": Thing()}, mode=MODE_PLAIN)


def test_attribute_access_returns_literal_in_tolerant_mode():
    class Thing:
        password = "hunter2"

    result = format_map(
        "{obj.password}", {"obj": Thing()}, mode=MODE_PLAIN, raise_on_missing=False
    )
    assert result == "{obj.password}"
    assert "hunter2" not in result


def test_format_spec_is_stripped():
    # Also blocks the ``{0:{1}}`` padding-based exfiltration trick.
    assert format_map("{x:>10}", {"x": "a"}, mode=MODE_PLAIN) == "a"
    assert format_map("{x:.100}", {"x": "abc"}, mode=MODE_PLAIN) == "abc"


@pytest.mark.parametrize("conversion", ("!r", "!s", "!a"))
def test_conversion_is_ignored(conversion):
    # !r on an EmailAlternativeString would otherwise leak its internal
    # (plain, html) pair via __repr__.
    plain_result = format_map("{x" + conversion + "}", {"x": "hello"}, mode=MODE_PLAIN)
    assert plain_result == "hello"
    html_result = format_map(
        "{x" + conversion + "}", {"x": "<b>hi</b>"}, mode=MODE_HTML
    )
    assert html_result == "&lt;b&gt;hi&lt;/b&gt;"


def test_conversion_does_not_leak_alternative_string_repr():
    alt = EmailAlternativeString("the plain form", "<b>the html form</b>")
    plain_result = format_map("Value: {x!r}", {"x": alt}, mode=MODE_PLAIN)
    assert "EmailAlternativeString(" not in plain_result
    assert plain_result == "Value: the plain form"
    html_result = format_map("Value: {x!s}", {"x": alt}, mode=MODE_HTML)
    assert "EmailAlternativeString(" not in html_result
    assert html_result == "Value: <b>the html form</b>"


def test_sequence_indexing_is_blocked():
    # Indexing would dereference on strings/lists/tuples.
    with pytest.raises(KeyError):
        format_map("{x[0]}", {"x": "abc"}, mode=MODE_PLAIN)
    assert (
        format_map("{x[0]}", {"x": "abc"}, mode=MODE_PLAIN, raise_on_missing=False)
        == "{x[0]}"
    )
    assert (
        format_map(
            "{x[2]}",
            {"x": "placeholder-surface"},
            mode=MODE_PLAIN,
            raise_on_missing=False,
        )
        == "{x[2]}"
    )


def test_dict_key_indexing_is_blocked():
    # Dicts aren't on the value allow-list, so the naive ``{x}`` path
    # raises too.
    with pytest.raises(TypeError):
        format_map("{x}", {"x": {"password": "hunter2"}}, mode=MODE_PLAIN)
    with pytest.raises(KeyError):
        format_map("{x[password]}", {"x": "surface"}, mode=MODE_PLAIN)
    tolerant = format_map(
        "{x[password]}", {"x": "surface"}, mode=MODE_PLAIN, raise_on_missing=False
    )
    assert "hunter2" not in tolerant


def test_non_string_placeholder_value_is_rejected():
    # Only allow-listed types pass; arbitrary objects are refused so
    # ``__str__``/``__repr__`` can't be used to smuggle internal state.
    class Thing:
        def __str__(self):
            return "<script>alert(1)</script>"

    with pytest.raises(TypeError):
        format_map("{x}", {"x": Thing()}, mode=MODE_PLAIN)
    with pytest.raises(TypeError):
        format_map("{x}", {"x": Thing()}, mode=MODE_HTML)
    with pytest.raises(TypeError):
        format_map("{x}", {"x": ["a", "b"]}, mode=MODE_PLAIN)
    with pytest.raises(TypeError):
        format_map("{x}", {"x": object()}, mode=MODE_PLAIN)


def test_allowed_value_types_round_trip():
    assert format_map("{x}", {"x": "hi"}, mode=MODE_PLAIN) == "hi"
    assert format_map("{x}", {"x": 42}, mode=MODE_PLAIN) == "42"
    assert format_map("{x}", {"x": 3.14}, mode=MODE_PLAIN) == "3.14"
    assert format_map("{x}", {"x": Decimal("19.95")}, mode=MODE_PLAIN) == "19.95"
    assert format_map("{x}", {"x": LazyI18nString("hello")}, mode=MODE_PLAIN) == "hello"
    assert format_map("{x}", {"x": mark_safe("safe")}, mode=MODE_PLAIN) == "safe"
    assert (
        format_map(
            "{x}", {"x": EmailAlternativeString("p", "<b>h</b>")}, mode=MODE_PLAIN
        )
        == "p"
    )


def test_format_map_refuses_to_double_format():
    once = format_map("Hi {name}", {"name": "Jane"})
    assert isinstance(once, FormattedString)
    with pytest.raises(SuspiciousOperation):
        format_map(once, {})


def test_mark_safe_value_stays_safe_after_format():
    url = mark_safe("https://foo.test/?x=1&y=2")
    result = format_map("{url}", {"url": url}, mode=MODE_HTML)
    assert isinstance(result, FormattedString)
    assert "&y=2" in result
    assert "&amp;y=2" not in result


def test_safe_string_mixed_with_escaped_content():
    context = {
        "url": mark_safe("https://foo.test/?a=1&b=2"),
        "name": "<script>alert(1)</script>",
    }
    result = format_map("{name} at {url}", context, mode=MODE_HTML)
    assert "<script>" not in result
    assert "&lt;script&gt;" in result
    assert "https://foo.test/?a=1&b=2" in result


def test_safe_string_input_detection():
    # Sanity check: our escape-bypass assumes mark_safe returns SafeString.
    assert isinstance(mark_safe("x"), SafeString)


def test_defuse_markdown_links_html_replaces_brackets():
    assert defuse_markdown_links("[click](url)") == "&#91;click&#93;(url)"


def test_defuse_markdown_links_html_leaves_other_chars_alone():
    assert defuse_markdown_links("no brackets here") == "no brackets here"
    assert defuse_markdown_links("<b>bold</b>") == "<b>bold</b>"


def test_defuse_markdown_links_html_handles_nested_brackets():
    assert defuse_markdown_links("[[nested]]") == "&#91;&#91;nested&#93;&#93;"


def test_defuse_markdown_links_plain_escapes_brackets():
    assert defuse_markdown_links("[click](url)", mode=MODE_PLAIN) == r"\[click\](url)"


def test_defuse_markdown_links_plain_escapes_backslash():
    assert defuse_markdown_links(r"\[escaped\]", mode=MODE_PLAIN) == r"\\\[escaped\\\]"


def test_defuse_markdown_links_plain_leaves_other_chars_alone():
    assert (
        defuse_markdown_links("no brackets here", mode=MODE_PLAIN) == "no brackets here"
    )
    assert (
        defuse_markdown_links("**bold** and _italic_", mode=MODE_PLAIN)
        == "**bold** and _italic_"
    )
    assert defuse_markdown_links("Jane (she/her)", mode=MODE_PLAIN) == "Jane (she/her)"


def test_email_alternative_accepts_plain_strings():
    alt = EmailAlternativeString("text", "<b>text</b>")
    assert alt.plain == "text"
    assert alt.html == "<b>text</b>"


def test_email_alternative_accepts_safe_strings():
    alt = EmailAlternativeString("text", mark_safe("<b>text</b>"))
    assert alt.html == "<b>text</b>"


@pytest.mark.parametrize(
    ("plain", "html"),
    (
        (None, "<b>h</b>"),
        ("p", None),
        (42, "<b>h</b>"),
        ("p", ["<b>h</b>"]),
        (object(), "h"),
        ("p", b"<b>h</b>"),
    ),
)
def test_email_alternative_rejects_non_string_values(plain, html):
    # Defence in depth: SafeFormatter._prepare_value's
    # EmailAlternativeString branch returns .plain/.html without
    # re-running the type allow-list, so enforce it at construction.
    with pytest.raises(TypeError, match="requires str values"):
        EmailAlternativeString(plain, html)


def test_formatted_string_survives_str_coercion():
    # Load-bearing: ``str(formatted)`` must stay a FormattedString so
    # the anti-double-format guard still fires after Django form fields
    # coerce bound initial values to display strings.
    once = format_map("Hi {name}", {"name": "Jane"})
    assert isinstance(once, FormattedString)

    coerced = str(once)

    assert type(coerced) is FormattedString
    assert coerced is once
    with pytest.raises(SuspiciousOperation):
        format_map(coerced, {})
