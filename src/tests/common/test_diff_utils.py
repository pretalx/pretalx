import pytest

from pretalx.common.diff_utils import detect_markdown, render_diff

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "text",
    (
        "**bold**",
        "_italic_",
        "[test](https://example.com)",
        "# Heading",
        "```code```",
        "- item",
        "* item",
        "+ item",
        "1. item",
        "> quote",
        "line1\nline2",
    ),
)
def test_detect_markdown_recognises_indicators(text):
    assert detect_markdown(text) is True


@pytest.mark.parametrize("text", (None, "", "plain text", 42))
def test_detect_markdown_rejects_non_markdown(text):
    assert detect_markdown(text) is False


@pytest.mark.parametrize(
    ("old", "new"),
    (
        (None, None),
        (None, "new text"),
        ("old text", None),
        ("", "new text"),
        ("old text", ""),
    ),
)
def test_render_diff_returns_no_diff_for_missing_values(old, new):
    result = render_diff(old, new)
    assert result["is_diff"] is False


def test_render_diff_produces_diff_for_two_strings():
    result = render_diff("hello world", "hello there")

    assert result["is_diff"] is True
    assert str(result["old_html"]) == "hello <del>world</del>"
    assert str(result["new_html"]) == "hello <ins>there</ins>"


def test_render_diff_escapes_html_in_content():
    result = render_diff("a <b>bold</b> word", "a <b>bold</b> change")

    assert result["is_diff"] is True
    assert str(result["old_html"]) == "a &lt;b&gt;bold&lt;/b&gt; <del>word</del>"
    assert str(result["new_html"]) == "a &lt;b&gt;bold&lt;/b&gt; <ins>change</ins>"


@pytest.mark.parametrize(
    ("old", "new", "threshold", "expected"),
    (("hi", "hello world", 200, False), ("hi there", "hello world", 2, True)),
)
def test_render_diff_threshold(old, new, threshold, expected):
    result = render_diff(old, new, threshold=threshold)
    assert result["is_diff"] is expected


def test_render_diff_non_string_values_skip_diff():
    result = render_diff(42, 99)
    assert result["is_diff"] is False


@pytest.mark.parametrize(
    ("old", "new", "expected_key"),
    (("**bold**", None, "old_html"), (None, "**bold**", "new_html")),
)
def test_render_diff_no_diff_renders_markdown_value(old, new, expected_key):
    """When diff is skipped but a value is markdown, its html is rendered."""
    result = render_diff(old, new)

    assert result["is_diff"] is False
    assert str(result[expected_key]) == "<p><strong>bold</strong></p>"


def test_render_diff_no_diff_omits_html_for_plain_text():
    """When diff is skipped and values are plain text, no html keys are added."""
    result = render_diff(None, "plain text")

    assert result["is_diff"] is False
    assert "new_html" not in result


def test_render_diff_markdown_content_renders_as_html():
    """When both values contain markdown, the diff output includes rendered markup."""
    result = render_diff("- old item", "- new item")

    assert result["is_diff"] is True
    assert str(result["old_html"]) == "<ul>\n<li><del>old</del> item</li>\n</ul>"
    assert str(result["new_html"]) == "<ul>\n<li><ins>new</ins> item</li>\n</ul>"


def test_render_diff_multiline_shows_added_line():
    result = render_diff("Line 1\nLine 2", "Line 1\nLine 2\nLine 3")

    assert result["is_diff"] is True
    assert str(result["old_html"]) == "<p>Line 1<br>\nLine 2</p>"
    assert str(result["new_html"]) == "<p>Line 1<br>\nLine 2<ins><br>\nLine 3</ins></p>"


def test_render_diff_markdown_list_addition():
    """Adding a second markdown list item produces both items in new_html."""
    old = "- [test](https://pretalx.com/)"
    new = "- [test](https://pretalx.com/)\n- second item"

    result = render_diff(old, new)

    assert result["is_diff"] is True
    old_html = str(result["old_html"])
    new_html = str(result["new_html"])
    # old side has one list item with the link
    assert old_html.startswith("<ul>\n<li><a href=")
    assert old_html.endswith("</a></li>\n</ul>")
    assert ">test</a>" in old_html
    # new side has two list items: the original link and the added text
    assert new_html.startswith("<ul>\n<li><a href=")
    assert "<li>second item</li>\n</ul>" in new_html
    assert ">test</a>" in new_html
