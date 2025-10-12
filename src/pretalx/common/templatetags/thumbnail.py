# SPDX-FileCopyrightText: 2024-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import template

from pretalx.common.image import get_thumbnail

register = template.Library()


@register.filter
def thumbnail(field, size):
    try:
        return get_thumbnail(field, size).url
    except Exception:
        return field.url if hasattr(field, "url") else None
