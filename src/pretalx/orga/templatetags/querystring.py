# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import template
from django.template.defaulttags import querystring as dj_querystring

register = template.Library()


@register.simple_tag(takes_context=True)
def django_querystring(context, **kwargs):
    """
    django_tables2 overrides django's querystring with its own
    incompatible version.

    https://github.com/jieter/django-tables2/issues/976
    """
    return dj_querystring(context, **kwargs)
