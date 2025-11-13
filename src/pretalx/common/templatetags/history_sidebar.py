# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import template

register = template.Library()


@register.inclusion_tag("common/logs.html", takes_context=True)
def history_sidebar(context, obj, limit=25, show_details_link=True):
    request = context.get("request")
    log_entries = obj.logged_actions()
    more_actions = False
    if limit:
        log_entries = list(log_entries[:limit])
        more_actions = len(log_entries) == limit

    return {
        "entries": log_entries,
        "object": obj,
        "request": request,
        "show_details_link": show_details_link,
        "show_more_link": show_details_link and more_actions,
        "history_class": "history-sidebar",
        "show_history_title": True,
    }
