# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import re

from diff_match_patch import diff_match_patch
from django.utils.html import escape
from django.utils.safestring import mark_safe


def detect_markdown(text):
    if not text or not isinstance(text, str):
        return False

    indicators = [
        r"\*",
        r"_",
        r"\[.*\]\(.*\)",
        r"^#{1,6}\s",
        r"```",
        r"^\s*[-*+]\s",
        r"^\s*\d+\.\s",
        r"^\s*>",
        r"\n",
    ]

    for pattern in indicators:
        if re.search(pattern, str(text), re.MULTILINE):
            return True

    return False


def render_diff(old_value, new_value, threshold=None):
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

    from pretalx.common.templatetags.rich_text import render_markdown

    if not should_diff:
        result = {"is_diff": False}
        if detect_markdown(old_value):
            result["old_html"] = mark_safe(render_markdown(old_value))
        if detect_markdown(new_value):
            result["new_html"] = mark_safe(render_markdown(new_value))
        return result

    # Calculate word-level diff
    dmp = diff_match_patch()
    old_words = re.split(r"(\s+)", old_str)
    new_words = re.split(r"(\s+)", new_str)
    # Use null byte as separator to avoid conflicts with content newlines
    separator = "\x00"
    old_text = separator.join(old_words)
    new_text = separator.join(new_words)
    diffs = dmp.diff_main(old_text, new_text)
    dmp.diff_cleanupSemantic(diffs)

    # Generate HTML for old and new versions
    old_html_parts = []
    new_html_parts = []
    for op, text in diffs:
        # Remove the separator, preserving original whitespace (including newlines)
        text = text.replace(separator, "")
        if op == diff_match_patch.DIFF_DELETE:
            old_html_parts.append(f"<del>{escape(text)}</del>")
        elif op == diff_match_patch.DIFF_INSERT:
            new_html_parts.append(f"<ins>{escape(text)}</ins>")
        elif op == diff_match_patch.DIFF_EQUAL:
            old_html_parts.append(escape(text))
            new_html_parts.append(escape(text))

    old_html = "".join(old_html_parts)
    new_html = "".join(new_html_parts)
    if detect_markdown(old_str) or detect_markdown(new_str):
        old_html = render_markdown(old_html)
        new_html = render_markdown(new_html)

    return {
        "is_diff": True,
        "old_html": mark_safe(old_html),
        "new_html": mark_safe(new_html),
    }
