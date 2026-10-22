# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import template

register = template.Library()


@register.filter(is_safe=True)
def title_segment(value):
    """Strip a page title segment and add the separator."""
    value = value.strip().removesuffix("::").strip()
    return f"{value} :: " if value else ""
