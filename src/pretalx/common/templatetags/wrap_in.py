# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import template
from django.utils.html import format_html

register = template.Library()


@register.filter
def wrap_in(content, tag_name):
    """Wrap escaped content in a static HTML tag.

    Use this instead of building markup with ``|add:``/``|safe`` around a
    dynamic value, e.g. to pass a highlighted variable into a blocktranslate.
    """
    return format_html(f"<{tag_name}>{{}}</{tag_name}>", content)
