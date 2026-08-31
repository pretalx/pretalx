# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms, template
from django.db import models
from django.utils.text import capfirst
from django.utils.translation import get_language

from pretalx.common.log import group_activity_log
from pretalx.common.tables import BooleanColumn

register = template.Library()


@register.inclusion_tag("common/includes/history_tab.html", takes_context=True)
def history_tab(context):
    return {
        "request": context.get("request"),
        "show_event": context.get("history_show_event", False),
        "activity_groups": group_activity_log(
            context.get("history_log_entries", ()),
            with_objects=context.get("history_with_objects", False),
        ),
    }


def resolve_choices(choices, value):
    if isinstance(value, (list, tuple)):
        return ", ".join(str(choices.get(item, item)) for item in value)
    return choices.get(value, value)


def form_field_choices(field):
    if not isinstance(field, forms.ChoiceField) or isinstance(
        field, forms.ModelChoiceField
    ):
        return {}
    return dict(field.choices)


def render_list(values):
    if not values:
        return ""
    return ", ".join(str(value) for value in values)


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
    from pretalx.common.text.diff import render_diff  # noqa: PLC0415 -- slow import

    event = context.get("request").event
    locale = event.locale if event else get_language()
    question = change.get("question")
    old_value = change.get("old")
    new_value = change.get("new")
    field_obj = change.get("field")
    form_field = change.get("form_field")
    label = question.question if question else change.get("label")
    if not label:
        label = field
    if not question:
        label = capfirst(label)

    result = {
        "label": label,
        "old": old_value,
        "new": new_value,
        "question": change.get("question"),
    }

    if "old_display" in change or "new_display" in change:
        result["old"] = change.get("old_display", old_value)
        result["new"] = change.get("new_display", new_value)
    elif (field_obj and isinstance(field_obj, models.BooleanField)) or isinstance(
        form_field, forms.BooleanField
    ):
        result["old"] = render_boolean(old_value)
        result["new"] = render_boolean(new_value)
    elif choices := (change.get("choices") or form_field_choices(form_field)):
        result["old"] = resolve_choices(choices, old_value)
        result["new"] = resolve_choices(choices, new_value)
    elif isinstance(old_value, (list, tuple)) or isinstance(new_value, (list, tuple)):
        result["old"] = render_list(old_value)
        result["new"] = render_list(new_value)
    elif getattr(log.content_object, f"get_{field}_display", None):
        result["old"] = get_display(log.content_object, field, old_value)
        result["new"] = get_display(log.content_object, field, new_value)
    elif isinstance(old_value, dict) or isinstance(new_value, dict):
        if not isinstance(old_value, dict):
            lang = next(iter(new_value)) if len(new_value) == 1 else locale
            old_value = {lang: old_value or ""}
        if not isinstance(new_value, dict):
            lang = next(iter(old_value)) if len(old_value) == 1 else locale
            new_value = {lang: new_value or ""}

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
        result["preformatted"] = isinstance(field_obj, models.FileField)
        result["diff_data"] = render_diff(
            old_value, new_value, markdown=not result["preformatted"]
        )

    return {"rows": [result], "field": field}
