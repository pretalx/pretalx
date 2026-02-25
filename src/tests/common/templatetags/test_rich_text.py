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
