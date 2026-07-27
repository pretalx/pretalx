# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.utils.html import format_html
from django.utils.safestring import SafeString, mark_safe

from pretalx.cfp.signals import html_head
from pretalx.common.templatetags.html_signal import html_signal

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_html_signal_no_receivers(event):
    result = html_signal("pretalx.cfp.signals.html_head", sender=event, request=None)
    assert result == ""


@pytest.mark.parametrize(
    ("response", "expected"),
    (
        (mark_safe("<div>test</div>"), "<div>test</div>"),
        ("<script>alert(1)</script>", "&lt;script&gt;alert(1)&lt;/script&gt;"),
        (
            format_html("<div>{}</div>", "<b>quoted</b>"),
            "<div>&lt;b&gt;quoted&lt;/b&gt;</div>",
        ),
    ),
    ids=("safe-kept", "unsafe-escaped", "format-html-kept"),
)
def test_html_signal_escapes_by_safety(
    event, register_signal_handler, response, expected
):
    def handler(signal, sender, **kwargs):
        return response

    register_signal_handler(html_head, handler)
    result = html_signal("pretalx.cfp.signals.html_head", sender=event, request=None)
    assert result == expected
    assert isinstance(result, SafeString)


def test_html_signal_concatenates_responses(event, register_signal_handler):
    def handler1(signal, sender, **kwargs):
        return mark_safe("<span>one</span>")

    def handler2(signal, sender, **kwargs):
        return mark_safe("<span>two</span>")

    register_signal_handler(html_head, handler1)
    register_signal_handler(html_head, handler2)
    result = html_signal("pretalx.cfp.signals.html_head", sender=event, request=None)
    assert "<span>one</span>" in result
    assert "<span>two</span>" in result


def test_html_signal_skips_none_responses(event, register_signal_handler):
    def handler(signal, sender, **kwargs):
        return None

    register_signal_handler(html_head, handler)
    result = html_signal("pretalx.cfp.signals.html_head", sender=event, request=None)
    assert result == ""
