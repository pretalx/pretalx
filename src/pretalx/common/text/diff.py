# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import re

from diff_match_patch import diff_match_patch
from django.utils.html import escape
from django.utils.safestring import mark_safe

from pretalx.common.templatetags.rich_text import render_markdown

_MARKDOWN_INDICATORS = tuple(
    re.compile(pattern, re.MULTILINE)
    for pattern in (
        r"\*",
        r"_",
        r"\[.*\]\(.*\)",
        r"^#{1,6}\s",
        r"```",
        r"^\s*[-*+]\s",
        r"^\s*\d+\.\s",
        r"^\s*>",
        r"\n",
    )
)

_TOKEN_SPLIT = re.compile(r"(\s+)")
# Markers that open a Markdown block.
_BLOCK_PREFIX = re.compile(r"^[ \t]*(?:(?:[-*+]|\d+\.)[ \t]+|#{1,6}[ \t]+|>[ \t]*)*")


def detect_markdown(text):
    if not text or not isinstance(text, str):
        return False

    return any(pattern.search(text) for pattern in _MARKDOWN_INDICATORS)


def _tokens_to_chars(*texts):
    # Map each whitespace-delimited token to a single character, same as
    # diff_match_patch does for line mode.
    token_array = [""]
    token_indices = {"": 0}

    def munge(text):
        chars = []
        for token in _TOKEN_SPLIT.split(text):
            if not token:
                continue
            index = token_indices.get(token)
            if index is None:
                token_array.append(token)
                index = token_indices[token] = len(token_array) - 1
            chars.append(chr(index))
        return "".join(chars)

    return [munge(text) for text in texts], token_array


def _render_change(tag, text, at_line_start):
    result = []
    for index, line in enumerate(text.split("\n")):
        if not line:
            result.append("")
            continue
        prefix = ""
        if index or at_line_start:
            prefix = _BLOCK_PREFIX.match(line).group(0)
        content = line[len(prefix) :]
        prefix = escape(prefix)
        result.append(
            f"{prefix}<{tag}>{escape(content)}</{tag}>" if content else prefix
        )
    return "\n".join(result)


def render_diff(old_value, new_value, threshold=None, markdown=True):
    """
    Render a diff between old and new values.

    Returns:
        dict with:
        - is_diff: bool indicating if diff was applied
        - old: original old value (if not diff)
        - new: original new value (if not diff)
        - old_html: rendered HTML for old value (if diff)
        - new_html: rendered HTML for new value (if diff)
    """
    old_str = str(old_value) if old_value is not None else ""
    new_str = str(new_value) if new_value is not None else ""

    should_diff = (
        isinstance(old_value, (str, type(None)))
        and isinstance(new_value, (str, type(None)))
        and old_value
        and new_value
        and (not threshold or (len(old_str) >= threshold or len(new_str) >= threshold))
    )

    if not should_diff:
        result = {"is_diff": False}
        if not markdown:
            return result
        if detect_markdown(old_value):
            result["old_html"] = mark_safe(render_markdown(old_value))  # noqa: S308  -- render_markdown sanitises
        if detect_markdown(new_value):
            result["new_html"] = mark_safe(render_markdown(new_value))  # noqa: S308  -- render_markdown sanitises
        return result

    # Calculate word-level diff
    dmp = diff_match_patch()
    (old_chars, new_chars), token_array = _tokens_to_chars(old_str, new_str)
    diffs = dmp.diff_main(old_chars, new_chars, False)
    dmp.diff_cleanupSemantic(diffs)

    # Generate HTML for old and new versions
    old_html_parts = []
    new_html_parts = []
    old_line_start = new_line_start = True
    for op, chars in diffs:
        text = "".join(token_array[ord(char)] for char in chars)
        if op == diff_match_patch.DIFF_DELETE:
            old_html_parts.append(_render_change("del", text, old_line_start))
            old_line_start = text.endswith("\n")
        elif op == diff_match_patch.DIFF_INSERT:
            new_html_parts.append(_render_change("ins", text, new_line_start))
            new_line_start = text.endswith("\n")
        else:
            old_html_parts.append(escape(text))
            new_html_parts.append(escape(text))
            old_line_start = new_line_start = text.endswith("\n")

    old_html = "".join(old_html_parts)
    new_html = "".join(new_html_parts)
    if markdown and (detect_markdown(old_str) or detect_markdown(new_str)):
        old_html = render_markdown(old_html)
        new_html = render_markdown(new_html)

    return {
        "is_diff": True,
        "old_html": mark_safe(old_html),  # noqa: S308  -- built from escape() and render_markdown
        "new_html": mark_safe(new_html),  # noqa: S308  -- built from escape() and render_markdown
    }
