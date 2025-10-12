# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import template
from django.utils.safestring import mark_safe

from pretalx.submission.icons import PLATFORM_ICONS

register = template.Library()


@register.simple_tag
def platform_icon(icon_name):
    if icon_name and icon_name in PLATFORM_ICONS:
        return mark_safe(PLATFORM_ICONS[icon_name])
    return ""
