# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import template
from django.utils.translation import gettext_lazy as _

register = template.Library()


@register.filter
def times(text: str):
    """Add a tag that really really really could be a standard tag."""
    if text is None:
        return ""
    str_text = str(text)
    if str_text == "1":
        return _("once")
    if str_text == "2":
        return _("twice")
    return _("{number} times").format(number=str_text)
