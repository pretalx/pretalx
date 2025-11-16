# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.common.diff_utils import detect_markdown, render_diff


def test_detect_markdown_bold():
    assert detect_markdown("**bold**")


def test_detect_markdown_italic():
    assert detect_markdown("_italic_")


def test_detect_markdown_link():
    assert detect_markdown("[test](https://example.com)")


def test_detect_markdown_heading():
    assert detect_markdown("# Heading")


def test_detect_markdown_code_block():
    assert detect_markdown("```code```")


def test_detect_markdown_list():
    assert detect_markdown("- item")


def test_detect_markdown_numbered_list():
    assert detect_markdown("1. item")


def test_detect_markdown_blockquote():
    assert detect_markdown("> quote")


def test_detect_markdown_newline():
    assert detect_markdown("line1\nline2")


def test_detect_markdown_rejects_plain_text():
    assert not detect_markdown("plain text")


def test_detect_markdown_rejects_none():
    assert not detect_markdown(None)


def test_detect_markdown_rejects_empty():
    assert not detect_markdown("")


def test_render_diff_no_diff_on_none_values():
    result = render_diff(None, None)
    assert result["is_diff"] is False


def test_render_diff_no_diff_on_empty_old():
    result = render_diff("", "new")
    assert result["is_diff"] is False


def test_render_diff_no_diff_on_empty_new():
    result = render_diff("old", "")
    assert result["is_diff"] is False


def test_render_diff_simple():
    result = render_diff("hello world", "hello there")
    assert result["is_diff"] is True
    assert "hello" in str(result["old_html"])
    assert "hello" in str(result["new_html"])


def test_render_diff_markdown_list_with_newlines():
    """Test that newlines in markdown lists are preserved in diffs."""
    old = "- [test](https://pretalx.com/)"
    new = (
        '- [test](https://pretalx.com/)\n- <i class="fa fa-paperclip"></i> double test'
    )

    result = render_diff(old, new)
    assert result["is_diff"] is True

    new_html_str = str(result["new_html"])
    assert new_html_str.count("<li>") >= 2, new_html_str


def test_render_diff_markdown_multiline():
    old = "Line 1\nLine 2"
    new = "Line 1\nLine 2\nLine 3"

    result = render_diff(old, new)
    assert result["is_diff"] is True
    new_html_str = str(result["new_html"])
    assert "Line 3" in new_html_str


def test_render_diff_threshold():
    short_text = "hi"
    result = render_diff(short_text, "hello world", threshold=200)
    assert result["is_diff"] is False
    result = render_diff("hi there", "hello world", threshold=2)
    assert result["is_diff"] is True
