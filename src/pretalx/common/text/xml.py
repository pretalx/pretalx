# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from xml.sax.saxutils import escape

STRIP_CONTROL_CHARS = dict.fromkeys(list(range(9)) + list(range(11, 32)))


def strip_control_characters(text):
    """Strip ASCII control characters that are invalid in XML 1.0."""
    return str(text or "").translate(STRIP_CONTROL_CHARS)


def xmlescape(text):
    """Escape text for safe inclusion in XML, stripping control chars."""
    text = str(text)
    text = text.translate(STRIP_CONTROL_CHARS)
    text = escape(text)  # escape ><&
    text = text.encode("ascii", "xmlcharrefreplace").decode()
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&apos;")
    return text
