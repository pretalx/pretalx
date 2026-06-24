# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.common.templatetags.rich_text import (
    link_callback,
    render_markdown,
    render_markdown_abslinks,
    render_markdown_plaintext,
    rich_text,
    rich_text_abslinks,
    rich_text_without_links,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("", ""),
        (None, ""),
        ("plain text", "plain text"),
        ("**bold** and *italic*", "bold and italic"),
        ("A [link](https://example.com) here", "A link here"),
        ("Line 1\nLine 2", "Line 1\nLine 2"),
        ("<script>alert('xss')</script>", "alert('xss')"),
    ),
)
def test_render_markdown_plaintext(text, expected):
    assert render_markdown_plaintext(text) == expected


@pytest.mark.parametrize("text", ("", None))
def test_render_markdown_empty(text):
    assert render_markdown(text) == ""


def test_render_markdown_produces_html():
    result = str(render_markdown("**bold**"))
    assert "<strong>bold</strong>" in result


def test_render_markdown_strips_dangerous_tags():
    result = str(render_markdown("<script>alert('xss')</script>"))
    assert "<script>" not in result


def test_render_markdown_strikethrough():
    """Custom ~~strikethrough~~ extension produces <del> tags."""
    result = str(render_markdown("~~deleted~~"))
    assert "<del>deleted</del>" in result


@pytest.mark.parametrize(
    ("text", "kind"),
    (
        # Matches
        ("intro\n- a\n- b", "list"),
        ("intro\n+ a\n+ b", "list"),
        ("intro\n* a\n* b", "list"),
        ("intro\n1. a\n2. b", "list"),
        # Not matching higher numbers
        ("intro\n2. a\n3. b", "para"),
        ("The year was\n2020. wild", "para"),
        ("intro\n10. a\n11. b", "para"),
        # Not matching empty markers (paragraph or heading)
        ("intro\n1.", "para"),
        ("intro\n- ", "heading"),
        ("Heading\n---", "heading"),
        # Not matching hrs
        ("intro\n* * *", "hr"),
        ("intro\n- - -", "hr"),
        # Not matching inside code blocks
        ("Run:\n```\n1. not a list\n- not a list\n```\ndone", "code"),
        ("Run:\n```\ncode line\n1. not a list\n```\ndone", "code"),
        ("Example:\n\n    code line\n    1. not a list", "code"),
    ),
)
def test_render_markdown_breakless_lists(text, kind):
    result = str(render_markdown(text))

    has_list = "<ul>" in result or "<ol" in result
    assert has_list is (kind == "list")
    assert ("<hr" in result) is (kind == "hr")
    if kind == "heading":
        assert "<h2" in result
    if kind == "code":
        assert "<li>" not in result
        assert "<code>" in result or "codehilite" in result


def test_render_markdown_breakless_list_keeps_intro_paragraph():
    result = str(render_markdown("Here are the options:\n- first\n- second"))

    assert "<p>Here are the options:</p>" in result
    assert "<li>first</li>" in result
    assert "<li>second</li>" in result
    assert "- first" not in result


def test_render_markdown_breakless_list_stays_tight():
    result = str(render_markdown("intro\n- a\n- b"))

    assert "<li>a</li>" in result
    assert "<li><p>" not in result


def test_render_markdown_breakless_ordered_only_interrupts_on_one():
    interrupting = str(render_markdown("intro\n1. a\n2. b"))
    assert "<ol>" in interrupting
    assert "<li>a</li>" in interrupting

    not_interrupting = str(render_markdown("intro\n2. a\n3. b"))
    assert "<ol" not in not_interrupting

    with_blank_line = str(render_markdown("intro\n\n2. a\n3. b"))
    assert "<ol" in with_blank_line
    assert "<li>a</li>" in with_blank_line


def test_render_markdown_breakless_does_not_split_code_block_content():
    result = str(render_markdown("```\ncode line\n1. still code\n```"))

    assert "<li>" not in result
    assert "\n\n" not in result.split("<code>")[1].split("</code>", maxsplit=1)[0]


def test_render_markdown_breakless_leaves_raw_html_block_untouched():
    result = str(render_markdown('<div markdown="0">\n- a\n- b\n</div>'))

    assert "<li>" not in result
    assert "- a" in result


@pytest.mark.parametrize(
    ("text", "link_substring", "has_noopener"),
    (
        ("foo.notatld", "foo.notatld", False),
        ("foo.com", "//foo.com", True),
        ("foo@bar.com", "mailto:foo@bar.com", False),
        ("chaos.social", "//chaos.social", True),
    ),
)
def test_rich_text_linkification(text, link_substring, has_noopener):
    result = rich_text(text)
    assert link_substring in result
    assert ('rel="noopener"' in result) is has_noopener
    assert ('target="_blank"' in result) is has_noopener


def test_rich_text_without_links_strips_anchors():
    result = str(rich_text_without_links("[click](https://example.com)"))
    assert "<a" not in result
    assert "click" in result


def test_rich_text_abslinks_uses_absolute_urls():
    """Absolute link rendering keeps the original URL instead of wrapping
    with safelink redirect."""
    result = str(rich_text_abslinks("https://example.com"))
    assert "https://example.com" in result
    assert 'target="_blank"' in result


@pytest.mark.parametrize("text", ("", None))
def test_render_markdown_abslinks_empty(text):
    assert render_markdown_abslinks(text) == ""


@pytest.mark.parametrize(
    "href", ("mailto:test@example.com", "tel:+123456", "/some/path")
)
def test_link_callback_passthrough_for_non_external_urls(href):
    """mailto:, tel:, and internal links are returned without modification."""
    attrs = {(None, "href"): href}
    result = link_callback(attrs, is_new=True, safelink=True)
    assert (None, "target") not in result
    assert result[(None, "href")] == href


def test_link_callback_external_with_safelink():
    attrs = {(None, "href"): "https://example.com"}
    result = link_callback(attrs, is_new=True, safelink=True)
    assert result[(None, "target")] == "_blank"
    assert result[(None, "rel")] == "noopener"
    assert "redirect" in result[(None, "href")]


def test_link_callback_external_without_safelink():
    attrs = {(None, "href"): "https://example.com"}
    result = link_callback(attrs, is_new=True, safelink=False)
    assert result[(None, "target")] == "_blank"
    assert result[(None, "rel")] == "noopener"
    assert result[(None, "href")] == "https://example.com"


def test_link_callback_no_href_defaults_to_slash():
    """Missing href attribute defaults to '/' which is internal."""
    attrs = {}
    result = link_callback(attrs, is_new=True, safelink=True)
    assert (None, "target") not in result
