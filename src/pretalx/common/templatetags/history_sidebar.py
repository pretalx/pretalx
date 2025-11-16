# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from contextlib import suppress

from django import template
from django.db import models

from pretalx.common.diff_utils import render_diff
from pretalx.common.tables import BooleanColumn

register = template.Library()


def resolve_foreign_key(field, value):
    if not value or not isinstance(field, models.ForeignKey):
        return value

    related_model = field.related_model
    with suppress(Exception):
        obj = related_model.objects.get(pk=value)
        return str(obj)

    return value


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


def render_boolean(value):

    if value:
        return BooleanColumn.TRUE_MARK
    return BooleanColumn.FALSE_MARK


def get_display(obj, field, value):
    obj.pk = None
    old_value = getattr(obj, field)
    setattr(obj, field, value)
    result = getattr(obj, f"get_{field}_display")()
    setattr(obj, field, old_value)
    return result


@register.inclusion_tag("common/change_row.html", takes_context=True)
def change_row(context, field, change, log):
    event = context.get("request").event
    question = change.get("question")
    old_value = change.get("old")
    new_value = change.get("new")
    field_obj = change.get("field")
    label = question.question if question else change.get("label")
    if not label and field_obj:
        label = field_obj.verbose_name
    if not label:
        label = field

    result = {
        "label": question.question if question else change.get("label", field),
        "old": old_value,
        "new": new_value,
        "question": change.get("question"),
    }

    if field_obj and isinstance(field_obj, models.ForeignKey):
        result["old"] = resolve_foreign_key(field_obj, old_value)
        result["new"] = resolve_foreign_key(field_obj, new_value)
    elif field_obj and isinstance(field_obj, models.BooleanField):
        result["old"] = render_boolean(old_value)
        result["new"] = render_boolean(new_value)
    elif getattr(log.content_object, f"get_{field}_display", None):
        result["old"] = get_display(log.content_object, field, old_value)
        result["new"] = get_display(log.content_object, field, new_value)
    elif getattr(field, "choices", None):
        choices = dict(field_obj.choices)
        result["old"] = choices.get(old_value, old_value)
        result["new"] = choices.get(new_value, new_value)
    elif isinstance(old_value, dict) or isinstance(new_value, dict):
        if not isinstance(old_value, dict):
            old_value = {event.locale: old_value or ""}
        if not isinstance(new_value, dict):
            new_value = {event.locale: new_value or ""}

        languages = set(old_value.keys()) | set(new_value.keys())
        rows = []
        for lang in languages:
            lang_old = old_value.get(lang)
            lang_new = new_value.get(lang)
            diff_data = render_diff(lang_old, lang_new)
            rows.append(
                {
                    "label": None,
                    "old": lang_old,
                    "new": lang_new,
                    "language": lang,
                    "question": change.get("question"),
                    "diff_data": diff_data,
                }
            )
        rows[0]["label"] = label
        rows[0]["rowspan"] = len(languages)
        return {"rows": rows, "field": field}
    else:
        result["diff_data"] = render_diff(old_value, new_value)

    return {
        "rows": [result],
        "field": field,
    }
