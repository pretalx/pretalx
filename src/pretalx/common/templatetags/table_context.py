# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import contextlib

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def bind_table_context(context, table):
    """Attach the rendering context to the table for TemplateColumn.

    django_tables2 does this in ``{% render_table %}``, which the htmx table
    partial never runs, so cell templates end up without ``request`` and
    without context processor data."""
    if getattr(table, "context", None) is None:
        with contextlib.suppress(AttributeError):
            table.context = context
    return ""
