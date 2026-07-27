# SPDX-FileCopyrightText: 2019-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import template
from django.utils.module_loading import import_string

from pretalx.common.signals import join_html_responses

register = template.Library()


@register.simple_tag
def html_signal(signal_name: str, **kwargs):
    """Send a signal and return the concatenated return values of all
    responses.

    Receivers must mark intentional HTML as safe (e.g. via ``format_html``
    or ``render_to_string``); any other response is escaped.
    """
    signal = import_string(signal_name)
    return join_html_responses(signal.send(**kwargs))
