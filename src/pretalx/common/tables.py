# SPDX-FileCopyrightText: 2023-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from urllib.parse import quote

import django_tables2 as tables
from django.db.models import OuterRef, Subquery
from django.db.models.lookups import Transform
from django.template import Context, Template
from django.template.loader import get_template
from django.utils.functional import cached_property
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django_tables2.utils import OrderBy, OrderByTuple

from pretalx.common.forms.tables import TablePreferencesForm


def get_icon(icon):
    return mark_safe(f'<i class="fa fa-{icon}"></i>')


class QuestionColumnMixin:
    """Mixin for tables that display QuestionColumns with answer caching."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self, "Meta") and hasattr(self.Meta, "model"):
            from pretalx.person.models import SpeakerProfile

            if self.Meta.model == SpeakerProfile:
                self._question_model = "user"
            else:
                self._question_model = "submission"

    def _get_question_columns(self):
        """Build list of question columns for extra_columns parameter."""
        extra_columns = []
        if not getattr(self, "short_questions", None):
            return extra_columns

        for question in self.short_questions:
            column_name = f"question_{question.id}"
            extra_columns.append(
                (
                    column_name,
                    QuestionColumn(
                        verbose_name=question.question,
                        question=question,
                    ),
                )
            )
        return extra_columns

    def get_answer_for_question(self, record, question_id):
        """Get answer object for a specific question, using lazy-loaded cache.

        This method fetches all answers for all records in the table in a single
        query the first time any question column is rendered. This is efficient
        because django-tables2 only renders visible columns.
        """
        if not getattr(self, "short_questions", None):
            return None

        if not hasattr(self, "_answers_cache"):
            self._load_all_answers()

        cache_key = self._get_record_cache_key(record)
        return self._answers_cache.get(cache_key, {}).get(question_id)

    def _get_record_cache_key(self, record):
        return record.user_id if self._question_model == "user" else record.pk

    def _get_answer_filter_field(self):
        model = "person" if self._question_model == "user" else "submission"
        return f"{model}_id__in"

    def _load_all_answers(self):
        from pretalx.submission.models import Answer

        record_ids = []
        try:
            for row in self.rows:
                record_ids.append(self._get_record_cache_key(row.record))
        except (AttributeError, TypeError):
            for record in self.data:
                record_ids.append(self._get_record_cache_key(record))

        if not record_ids:
            self._answers_cache = {}
            return

        filter_field = self._get_answer_filter_field()
        answers = (
            Answer.objects.filter(
                **{filter_field: record_ids},
                question__in=self.short_questions,
            )
            .select_related("question")
            .prefetch_related("options")
        )
        self._answers_cache = {}
        cache_key = "person_id" if self._question_model == "user" else "submission_id"
        for answer in answers:
            answer_key = getattr(answer, cache_key, None)
            self._answers_cache.setdefault(answer_key, {})[answer.question_id] = answer


class PretalxTable(tables.Table):
    exempt_columns = ("pk", "actions")

    def __init__(
        self,
        *args,
        event=None,
        user=None,
        has_update_permission=False,
        has_delete_permission=False,
        **kwargs,
    ):
        self.event = event
        self.user = user
        self.has_update_permission = has_update_permission
        self.has_delete_permission = has_delete_permission
        self._ordering_applied = False
        super().__init__(*args, **kwargs)

    @tables.Table.order_by.setter
    def order_by(self, value):
        """Override order_by setter to prevent django_tables2 from re-ordering.

        After our configure() method applies custom multi-column ordering, we set
        _ordering_applied=True. This prevents RequestConfig from triggering the
        default ordering mechanism which doesn't handle function-based columns
        correctly in multi-column scenarios.
        """
        if self._ordering_applied:
            # Don't re-order - just update the display value for sort indicators
            order_by = () if not value else value
            order_by = order_by.split(",") if isinstance(order_by, str) else order_by
            valid = []
            for alias in order_by:
                name = OrderBy(alias).bare
                if name in self.columns and self.columns[name].orderable:
                    valid.append(alias)
            self._order_by = OrderByTuple(valid)
            # Don't call self.data.order_by()
        else:
            # Use parent's setter which includes ordering
            tables.Table.order_by.fset(self, value)

    @property
    def name(self):
        return self.__class__.__name__

    def _get_columns(self, visible=True):
        columns = []
        for name, column in self.columns.items():
            if column.visible == visible and name not in self.exempt_columns:
                columns.append((name, column.verbose_name))
        return columns

    @property
    def available_columns(self):
        return self._get_columns(visible=False)

    @property
    def selected_columns(self):
        return self._get_columns(visible=True)

    @property
    def current_ordering(self):
        if not self.order_by:
            return []
        result = []
        for field in self.order_by:
            if field.startswith("-"):
                result.append({"column": field[1:], "direction": "desc"})
            else:
                result.append({"column": field, "direction": "asc"})
        return result

    @cached_property
    def configuration_form(self):
        has_default_columns = getattr(self, "default_columns", None)
        has_hidden_columns = len(self.available_columns) > 0

        if not (has_default_columns or has_hidden_columns):
            return None

        return TablePreferencesForm(table=self)

    def _set_columns(self, selected_columns):
        available_column_names = self.columns.names()
        valid_selected_columns = [
            c for c in selected_columns if c in available_column_names
        ]
        visible_columns = [*valid_selected_columns, *self.exempt_columns]

        for column_name in available_column_names:
            if column_name in visible_columns:
                self.columns.show(column_name)
            else:
                self.columns.hide(column_name)

        # Rearrange the sequence to list selected columns first, followed by all remaining columns
        self.sequence = [
            *valid_selected_columns,
            *[c for c in available_column_names if c not in valid_selected_columns],
        ]

        if "pk" in self.sequence:
            self.sequence.remove("pk")
            self.sequence.insert(0, "pk")
        if "actions" in self.sequence:
            self.sequence.remove("actions")
            self.sequence.append("actions")

    def _get_sortable_column_names(self):
        return {
            name
            for name, column in self.columns.items()
            if column.orderable and name not in self.exempt_columns
        }

    def _validate_ordering(self, ordering):
        if not ordering:
            return ordering
        sortable = self._get_sortable_column_names()
        valid_ordering = []
        seen_columns = set()
        for field in ordering:
            column_name = field[1:] if field.startswith("-") else field
            if column_name in sortable and column_name not in seen_columns:
                valid_ordering.append(field)
                seen_columns.add(column_name)
        return valid_ordering if valid_ordering else None

    def _apply_ordering(self, queryset, ordering):
        """Apply multi-column ordering to the queryset, handling function-based columns.

        django_tables2's default ordering mechanism (TableQuerysetData.order_by) has a
        limitation: when a column's order() method returns modified=True, it stops
        processing subsequent columns. This means multi-column sorting doesn't work
        when function-based columns are involved.

        This method applies all ordering ourselves by:
        1. Iterating through all columns in the ordering
        2. For function-based columns (FunctionOrderMixin), applying their annotation
        3. For traditional columns, using their accessor
        4. Applying all orderings at once with a single order_by() call

        This ensures multi-column sorting works correctly even when mixing function-based
        and traditional columns.
        """
        if not ordering:
            return queryset

        order_by_fields = []
        for field in ordering:
            descending = field.startswith("-")
            column_name = field[1:] if descending else field
            if column_name not in self.columns:
                continue

            bound_column = self.columns[column_name]
            column = bound_column.column

            # Check if this is a FunctionOrderMixin column
            if (
                hasattr(column, "apply_function_ordering")
                and column.order_function_lookup
            ):
                queryset, order_keys = column.apply_function_ordering(
                    queryset, descending
                )
                order_by_fields.extend(order_keys)
            elif bound_column.order_by:
                for accessor in bound_column.order_by:
                    accessor_str = str(accessor)
                    if descending and not accessor_str.startswith("-"):
                        order_by_fields.append(f"-{accessor_str}")
                    elif not descending and accessor_str.startswith("-"):
                        order_by_fields.append(accessor_str[1:])
                    else:
                        order_by_fields.append(accessor_str)
            else:
                order_key = f"-{column_name}" if descending else column_name
                order_by_fields.append(order_key)

        if order_by_fields:
            queryset = queryset.order_by(*order_by_fields)

        return queryset

    def _merge_ordering(self, new_ordering, saved_ordering):
        """Merge new column click ordering with saved multi-column ordering.

        When user clicks a column header, we receive the new primary sort.
        Preserve the secondary sort if present; _validate_ordering will
        handle deduplication if the same column appears in both positions.
        """
        new_ordering = [s for s in new_ordering if s]
        saved_ordering = [s for s in saved_ordering if s]
        if not saved_ordering or not new_ordering:
            return new_ordering
        if len(new_ordering) == 2 or len(saved_ordering) == 1:
            return new_ordering
        return [new_ordering[0], saved_ordering[1]]

    def configure(self, request):
        columns = None
        ordering = None
        page_size = None

        # If an ordering has been specified as a query parameter, save it as the
        # user's preferred ordering for this table.
        if request.user.is_authenticated and self.event:
            preferences = request.user.get_event_preferences(self.event)
            saved_ordering = preferences.get(f"tables.{self.name}.ordering")

            if new_ordering := request.GET.getlist(self.prefixed_order_by_field):
                ordering = self._merge_ordering(new_ordering, saved_ordering)
                if ordering := self._validate_ordering(ordering):
                    preferences.set(
                        f"tables.{self.name}.ordering", ordering, commit=True
                    )
            else:
                ordering = saved_ordering

            columns = preferences.get(f"tables.{self.name}.columns")
            page_size = preferences.get(f"tables.{self.name}.page_size")

        columns = columns or getattr(self, "default_columns", None) or self.Meta.fields
        self._set_columns(columns)

        if ordering:
            # Apply our custom ordering that handles multi-column sorting with
            # function-based columns correctly. We modify the underlying queryset
            # directly and set _order_by for display purposes only.
            self.data.data = self._apply_ordering(self.data.data, ordering)
            self._order_by = OrderByTuple(ordering)
            self._ordering_applied = True

        return page_size


class UnsortableMixin:
    def __init__(self, *args, **kwargs):
        # Prevent ordering of dragsort tables
        kwargs["orderable"] = False
        kwargs["order_by"] = None
        super().__init__(*args, **kwargs)


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
                if getattr(lookup, "source_expressions", None):
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
    - Pass the request to the render method, allowing use of queryparam
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
        context = getattr(table, "context", Context())
        for key, value in self.template_context.items():
            if callable(value):
                context[key] = value(record, table)
            else:
                context[key] = value
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
    attrs = {"td": {"class": "text-end"}}
    empty_values = ()
    default_actions = {
        "edit": {
            "title": _("edit"),
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
        return mark_safe(html)


class BooleanColumn(tables.Column):
    TRUE_MARK = mark_safe('<i class="fa fa-check-circle text-success"></i>')
    FALSE_MARK = mark_safe('<i class="fa fa-times-circle text-danger"></i>')
    EMPTY_MARK = mark_safe('<span class="text-muted">&mdash;</span>')
    attrs = {
        "td": {"class": "text-center"},
        "th": {"class": "text-center"},
    }

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

    def order(self, queryset, is_descending):
        from pretalx.submission.models import Answer

        if hasattr(queryset.model, "user"):
            answer_subquery = Answer.objects.filter(
                person_id=OuterRef("user_id"), question_id=self.question.id
            ).values("answer")[:1]
        else:
            answer_subquery = Answer.objects.filter(
                submission_id=OuterRef("pk"), question_id=self.question.id
            ).values("answer")[:1]

        annotation_name = f"_question_{self.question.id}_answer"
        queryset = queryset.annotate(**{annotation_name: Subquery(answer_subquery)})
        order_field = f"{'-' if is_descending else ''}{annotation_name}"
        queryset = queryset.order_by(order_field)
        return queryset, True

    def render(self, record, table, value, bound_column, **kwargs):
        answer = table.get_answer_for_question(record, self.question.id)

        if not answer:
            return self.placeholder

        context = getattr(table, "context", {})
        context["answer"] = answer
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
