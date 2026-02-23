# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django.utils.safestring
from django import template
from django.utils.translation import gettext_lazy as _

register = template.Library()


@register.filter
def copyable(value):
    value = str(value)
    if '"' in value:
        return value
    title = str(_("Copy"))
    success_message = str(_("Copied!"))
    error_message = str(_("Failed to copy"))
    html = f"""
    <span data-destination="{value}"
            class="copyable-text"
            data-toggle="tooltip"
            data-placement="top"
            title="{title}"
            data-success-message="{success_message}"
            data-error-message="{error_message}"
            role="button"
            tabindex="0"
    >
        {value}
    </span>"""
    return django.utils.safestring.mark_safe(html)  # noqa: S308  -- value is escaped in template
