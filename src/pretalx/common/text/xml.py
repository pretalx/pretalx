# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from xml.sax.saxutils import escape

STRIP_CONTROL_CHARS = dict.fromkeys(
    # - C0 controls except tab (0x09) and newline (0x0a), DEL (0x7f)
    # - C1 controls (0x80-0x9f) for term escapes with 0x9b
    list(range(9)) + list(range(11, 32)) + list(range(127, 160))
)


def strip_control_characters(text):
    """Strip control characters that can corrupt exports or inject terminal escapes."""
    return str(text or "").translate(STRIP_CONTROL_CHARS)


def strip_control_characters_deep(data):
    if isinstance(data, dict):
        return {
            strip_control_characters_deep(key): strip_control_characters_deep(value)
            for key, value in data.items()
        }
    if isinstance(data, (list, tuple)):
        return type(data)(strip_control_characters_deep(item) for item in data)
    if data is None or isinstance(data, (bool, int, float)):
        return data
    return strip_control_characters(data)


def xmlescape(text):
    """Escape text for safe inclusion in XML, stripping control chars."""
    text = str(text)
    text = text.translate(STRIP_CONTROL_CHARS)
    text = escape(text)  # escape ><&
    text = text.encode("ascii", "xmlcharrefreplace").decode()
    text = text.replace('"', "&quot;")
    return text.replace("'", "&apos;")
