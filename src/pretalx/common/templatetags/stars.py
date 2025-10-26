# SPDX-FileCopyrightText: 2025-present Florian Moesch
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def stars(stars: int, max_stars: int = 5):
    result = '<span class="star-rating">'
    if stars is None:
        return ""
    for i in range(max_stars):
        if i < stars:
            result += '<span class="star color-active"><i class="fa fa-star fa-lg"></i></span>'
        else:
            result += '<span class="star"><i class="fa fa-star-o fa-lg"></i></span>'
    result += "</span>"
    return mark_safe(result)
