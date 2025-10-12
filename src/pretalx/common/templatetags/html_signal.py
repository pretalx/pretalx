# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import template
from django.utils.module_loading import import_string
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def html_signal(signal_name: str, **kwargs):
    """Send a signal and return the concatenated return values of all
    responses.

    Usage::

        {% html_signal "path.to.signal" argument="value" ... %}
    """
    signal = import_string(signal_name)
    _html = []
    for _receiver, response in signal.send(**kwargs):
        if response:
            _html.append(response)
    return mark_safe("".join(_html))
