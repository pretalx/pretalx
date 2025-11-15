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


@register.inclusion_tag("common/change_row.html", takes_context=True)
def change_row(context, field, change):
    event = context.get("request").event
    rows = []

    question = change.get("question")
    label = question.question if question else change.get("label", field)
    old_value = change.get("old")
    new_value = change.get("new")
    is_i18n = isinstance(old_value, dict) or isinstance(new_value, dict)

    if is_i18n:
        if not isinstance(old_value, dict):
            old_value = {event.locale: old_value or ""}
        if not isinstance(new_value, dict):
            new_value = {event.locale: new_value or ""}

        languages = set(old_value.keys()) | set(new_value.keys())
        for lang in languages:
            rows.append(
                {
                    "label": None,
                    "old": old_value.get(lang),
                    "new": new_value.get(lang),
                    "language": lang,
                    "question": change.get("question"),
                }
            )
        rows[0]["label"] = label
        rows[0]["rowspan"] = len(languages)
    else:
        rows.append(
            {
                "label": label,
                "old": old_value,
                "new": new_value,
                "language": None,
                "question": change.get("question"),
            }
        )

    return {
        "rows": rows,
        "field": field,
    }
