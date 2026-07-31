# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
from django.utils.html import escape
from django.utils.safestring import SafeString
from django.utils.translation import gettext_lazy as _

from pretalx.common.templatetags.rich_text import render_mail_body
from pretalx.common.text.formatting import (
    MODE_HTML,
    MODE_PLAIN,
    SafeFormatter,
    format_map,
)
from pretalx.mail.domain.render import get_prefixed_subject

PLACEHOLDER_MARKER_CLASS = "placeholder"
PLACEHOLDER_MARKER_TITLE = _("This value will be replaced based on dynamic parameters.")

_STATE_TEXT = 0
_STATE_LINK_TARGET = 1
_STATE_CODE = 2


def mark_placeholder_value(value):
    return (
        f'<span class="{PLACEHOLDER_MARKER_CLASS}" '
        f'title="{escape(PLACEHOLDER_MARKER_TITLE)}">{value}</span>'
    )


def _scan_markdown_state(text, state):
    for index, char in enumerate(text):
        if char == "\n":
            state = _STATE_TEXT
        elif state == _STATE_CODE:
            if char == "`":
                state = _STATE_TEXT
        elif state == _STATE_LINK_TARGET:
            if char == ")":
                state = _STATE_TEXT
        elif char == "`":
            state = _STATE_CODE
        elif char == "(" and index and text[index - 1] == "]":
            state = _STATE_LINK_TARGET
    return state


class PreviewFormatter(SafeFormatter):
    def _prepare_value(self, value):
        is_safe = isinstance(value, SafeString)
        value = super()._prepare_value(value)
        if self.mode == MODE_PLAIN and not is_safe:
            value = escape(value)
        return value

    def vformat(self, format_string, args, kwargs):
        result = []
        scan_markdown = self.mode == MODE_HTML
        state = _STATE_TEXT
        for literal_text, field_name, _format_spec, _conversion in self.parse(
            format_string
        ):
            result.append(literal_text)
            if scan_markdown:
                state = _scan_markdown_state(literal_text, state)
            if field_name is None:
                continue
            value = self.format_field(self.get_value(field_name, args, kwargs), "")
            result.append(
                value if state != _STATE_TEXT else mark_placeholder_value(value)
            )
        return "".join(result)


def build_preview_context(placeholders, event):
    return {
        identifier: escape(placeholder.render_sample(event))
        for identifier, placeholder in placeholders.items()
    }


def render_preview_subject(subject, context, event):
    import bleach  # noqa: PLC0415 -- slow import

    subject = bleach.clean(subject, tags={})
    return get_prefixed_subject(
        event, format_map(subject, context, mode=MODE_PLAIN, formatter=PreviewFormatter)
    )


def render_preview_body(text, context):
    return render_mail_body(
        format_map(text, context, mode=MODE_HTML, formatter=PreviewFormatter)
    )
