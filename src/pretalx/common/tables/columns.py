# SPDX-FileCopyrightText: 2023-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from urllib.parse import quote

import django_tables2 as tables
from django.db.models import OuterRef, Subquery
from django.db.models.lookups import Transform
from django.template import Context, Template
from django.template.loader import get_template
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from pretalx.submission.models import Answer


def get_icon(icon):
    return mark_safe(f'<i class="fa fa-{icon}"></i>')  # noqa: S308  -- static icon markup


class FunctionOrderMixin:
    """Mixin for columns that use Django ORM functions/expressions for ordering.

    This mixin stores the ordering function in order_function_lookup, which is then
    used by PretalxTable._apply_ordering() to handle multi-column sorting correctly.

    Note: The order() method is kept for backward compatibility with django_tables2's
    single-column ordering. For multi-column sorting with function-based columns,
    PretalxTable._apply_ordering() is used instead, which properly handles all columns
    in sequence without the early-return limitation of django_tables2's default mechanism.
    """

    def __init__(self, *args, order_by=None, **kwargs):
        self.order_function_lookup = {}
        if order_by:
            if not isinstance(order_by, (list, tuple)):
                order_by = (order_by,)
            plain_order_by = []
            for key in order_by:
                if isinstance(key, str):
                    plain_order_by.append(key)
                    continue

                lookup = key
                while isinstance(lookup.source_expressions[0], Transform):
                    lookup = lookup.source_expressions[0]

                plain_field = lookup.source_expressions[0].name
                self.order_function_lookup[plain_field] = key
                plain_order_by.append(plain_field)
            order_by = plain_order_by

        super().__init__(*args, order_by=order_by, **kwargs)

    def apply_function_ordering(self, queryset, descending):
        """Apply function-based annotations and return (queryset, order_keys).

        This method is used by both:
        - order() for django_tables2's single-column ordering
        - PretalxTable._apply_ordering() for multi-column sorting

        Returns a tuple of (annotated_queryset, list_of_order_keys).
        """
        order_keys = []
        for plain_field, func in self.order_function_lookup.items():
            annotation_key = f"_sort_{plain_field.replace('__', '_')}"
            queryset = queryset.annotate(**{annotation_key: func})
            if descending:
                annotation_key = f"-{annotation_key}"
            order_keys.append(annotation_key)
        return queryset, order_keys

    def order(self, queryset, is_descending):
        """Apply function-based ordering to the queryset.

        Note: This method is called by django_tables2's TableQuerysetData.order_by()
        for single-column ordering scenarios. For multi-column sorting in PretalxTable,
        we use _apply_ordering() instead which reads order_function_lookup directly.

        The limitation in django_tables2 is that when any column's order() returns
        modified=True, it stops processing subsequent columns. Our _apply_ordering()
        method handles all columns correctly regardless of whether they use functions.
        """
        if not self.order_function_lookup:
            return (queryset, False)
        queryset, order_keys = self.apply_function_ordering(queryset, is_descending)
        queryset = queryset.order_by(*order_keys)
        return (queryset, True)


class SortableColumn(FunctionOrderMixin, tables.Column):
    pass


class TemplateColumn(tables.TemplateColumn):
    """
    Overrides the default django-tables2 TemplateColumn.
    Changes:
    - Allow to change the context_object_name
    - Pass the request to the render method, allowing use of querystring
    - Return a placeholder if the rendered value is empty
    """

    context_object_name = "record"
    placeholder = mark_safe("&mdash;")

    def __init__(self, *args, template_context=None, **kwargs):
        if name := kwargs.pop("context_object_name", None):
            self.context_object_name = name
        self.template_context = template_context or {}
        super().__init__(*args, **kwargs)

    def render(self, record, table, value, bound_column, **kwargs):
        # We can’t call super() here, because there is no way to inject
        # extra context into TemplateColumn.
        # So instead we’re adding our own extra context here and then
        # proceed with the vendored TemplateColumn.render() method
        context = getattr(table, "context", None) or {}
        context["table"] = table
        if not isinstance(context, Context):
            context = Context(context)
        for key, context_value in self.template_context.items():
            if callable(context_value):
                context[key] = context_value(record, table)
            else:
                context[key] = context_value
        context[self.context_object_name] = record

        additional_context = {
            "default": bound_column.default,
            "column": bound_column,
            "record": record,
            "value": value,
            "row_counter": kwargs["bound_row"].row_counter,
        }
        additional_context.update(self.extra_context)
        with context.update(additional_context):
            if self.template_code:
                result = Template(self.template_code).render(context)
            else:
                result = get_template(self.template_name).render(
                    context.flatten(), request=table.request
                )
            if not result.strip():
                return self.placeholder
            return result

    def value(self, **kwargs):
        result = super().value(**kwargs)
        if result == self.placeholder:
            return ""
        return result


class SortableTemplateColumn(FunctionOrderMixin, TemplateColumn):
    pass


class ActionsColumn(tables.Column):
    attrs = {"th": {"class": "d-print-none"}, "td": {"class": "text-end d-print-none"}}
    empty_values = ()
    default_actions = {
        "edit": {
            "title": _("Edit"),
            "icon": "edit",
            "url": "urls.edit",
            "color": "info",
            "condition": None,
            "permission": "update",
        },
        "delete": {
            "title": _("Delete"),
            "icon": "trash",
            "url": "urls.delete",
            "next_url": True,
            "color": "danger",
            "condition": None,
            "permission": "delete",
        },
        "sort": {
            "title": _("Move item"),
            "icon": "arrows",
            "color": "primary",
            "extra_class": "dragsort-button",
            "extra_attrs": 'draggable="true"',
            "condition": None,
            "permission": "update",
        },
        "copy": {
            "icon": "copy",
            "title": _("Copy access code link"),
            "extra_class": "copyable-text",
            "color": "info",
            "permission": "update",
        },
        "send": {
            "icon": "envelope",
            "color": "info",
            "url": "urls.send",
            "permission": "update",
        },
    }

    def __init__(self, *args, actions=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.orderable = False

        self.actions = {}
        for key, value in actions.items():
            self.actions[key] = self.default_actions.get(key, {}).copy()
            self.actions[key].update(value)

    def header(self):
        # Don't ever show a column title
        return ""

    def render(self, record, table, **kwargs):
        if not self.actions or not getattr(record, "pk", None):
            return ""

        request = getattr(table, "context", {}).get("request")
        user = getattr(request, "user", None)

        html = ""
        for action in self.actions.values():
            if user and (permission := action.get("permission")):
                perm_name = f"has_{permission}_permission"
                if hasattr(table, perm_name):
                    if not getattr(table, perm_name):
                        continue
                elif not user.has_perm(permission, record):
                    continue
            if (condition := action.get("condition")) and not condition(record):
                continue

            extra_class = action.get("extra_class") or ""
            extra_class = f" {extra_class}" if extra_class else ""
            extra_attrs = action.get("extra_attrs") or ""
            if callable(extra_attrs):
                extra_attrs = extra_attrs(record)
            extra_attrs = f" {extra_attrs}" if extra_attrs else ""
            inner_html = ""
            if title := action.get("title"):
                inner_html += f'title="{title}" '
            inner_html += (
                f'class="btn btn-sm btn-{action["color"]}{extra_class}"{extra_attrs}>'
            )
            if icon := action.get("icon"):
                inner_html += get_icon(icon)
            if label := action.get("label"):
                inner_html += label

            # url is a dotted string to be accessed on the record
            url = action.get("url")
            if not url:
                # Render button and hope there is some JS to handle it
                html += f"<button {inner_html}</button>"
            else:
                if callable(url):
                    url = url(record)
                else:
                    url_parts = url.split(".")
                    url = record
                    for part in url_parts:
                        url = getattr(url, part)
                        if callable(url):
                            url = url()
                if action.get("next_url") and request:
                    url = f"{url}?next={quote(request.get_full_path())}"
                html += f'<a href="{url}" {inner_html}</a>'
        html = f'<div class="action-column">{html}</div>'
        return mark_safe(html)  # noqa: S308  -- built from escaped URLs and static markup


class BooleanColumn(tables.Column):
    TRUE_MARK = mark_safe('<i class="fa fa-check-circle text-success"></i>')  # noqa: S308  -- static icon markup
    FALSE_MARK = mark_safe('<i class="fa fa-times-circle text-danger"></i>')  # noqa: S308  -- static icon markup
    EMPTY_MARK = mark_safe('<span class="text-muted">&mdash;</span>')
    attrs = {"td": {"class": "text-center"}, "th": {"class": "text-center"}}

    def render(self, value):
        if value is None:
            return self.EMPTY_MARK
        return self.TRUE_MARK if value else self.FALSE_MARK


class DateTimeColumn(tables.DateTimeColumn):
    timezone = None
    placeholder = mark_safe("&mdash;")

    def render(self, record, table, value, bound_column, **kwargs):
        if not value:
            return self.placeholder
        if value and table and (event := getattr(table, "event", None)):
            value = value.astimezone(event.tz)
        return f"{value.date().isoformat()} {value.time().strftime('%H:%M')}"

    def value(self, value):
        if value:
            return value.isoformat()


class QuestionColumn(TemplateColumn):
    """Column for rendering question answers using the standard question template.

    This column delegates to the table's get_answer_for_question method,
    which should handle caching and efficient data fetching.
    """

    empty_values = ()  # Always call render, even if no value from accessor
    placeholder = mark_safe("&mdash;")

    def __init__(self, *args, question=None, **kwargs):
        self.question = question
        kwargs.setdefault("orderable", True)
        kwargs.setdefault("template_name", "common/question_answer.html")
        kwargs.setdefault("attrs", {})
        if "td" not in kwargs["attrs"]:
            kwargs["attrs"]["td"] = {"class": ""}
        existing_class = kwargs["attrs"]["td"].get("class", "")
        kwargs["attrs"]["td"]["class"] = f"{existing_class} answer".strip()
        super().__init__(*args, **kwargs)

    def apply_custom_ordering(self, queryset, is_descending):
        """Apply annotation for ordering and return (queryset, order_keys).

        Used by PretalxTable._apply_ordering() for multi-column sorting.
        This method only annotates - it does NOT call order_by().
        """
        if hasattr(queryset.model, "user"):
            answer_subquery = Answer.objects.filter(
                speaker_id=OuterRef("pk"), question_id=self.question.id
            ).values("answer")[:1]
        else:
            answer_subquery = Answer.objects.filter(
                submission_id=OuterRef("pk"), question_id=self.question.id
            ).values("answer")[:1]

        annotation_name = f"_question_{self.question.id}_answer"
        queryset = queryset.annotate(**{annotation_name: Subquery(answer_subquery)})
        order_field = f"{'-' if is_descending else ''}{annotation_name}"
        return queryset, [order_field]

    def order(self, queryset, is_descending):
        """Apply ordering for single-column sorting (django-tables2 default mechanism)."""
        queryset, order_keys = self.apply_custom_ordering(queryset, is_descending)
        queryset = queryset.order_by(*order_keys)
        return queryset, True

    def render(self, record, table, value, bound_column, **kwargs):
        answer = table.get_answer_for_question(record, self.question.id)

        if not answer:
            return self.placeholder

        # Ensure table.context exists so TemplateColumn.render() sees our answer
        # Must be a Django Context object, not a plain dict, for update() context manager
        if not hasattr(table, "context") or table.context is None:
            table.context = Context()
        table.context["answer"] = answer
        return super().render(record, table, value, bound_column, **kwargs)


class IndependentScoreColumn(tables.Column):
    empty_values = ()  # Always call render, even if no value from accessor
    placeholder = mark_safe("&mdash;")

    def __init__(self, *args, category=None, **kwargs):
        self.category = category
        kwargs.setdefault("orderable", False)
        super().__init__(*args, **kwargs)

    def render(self, record, table, **kwargs):
        score = table.get_independent_score(record, self.category.pk)
        return score if score is not None else self.placeholder
