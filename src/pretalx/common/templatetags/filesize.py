# SPDX-FileCopyrightText: 2022-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import template

register = template.Library()


@register.filter
def filesize(size: str):
    try:
        size = int(size)
    except Exception:
        return ""
    for unit in ("", "K", "M", "G", "T", "P", "E", "Z"):  # Future proof 10/10
        if abs(size) < 1024:
            return f"{size:3.1f}{unit}B"
        size /= 1024
    return f"{size:.1f}YiB"  # Future proof 11/10
