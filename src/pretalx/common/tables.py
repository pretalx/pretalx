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
        super().__init__(*args, **kwargs)

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

    def configure(self, request):
        columns = None
        ordering = None
        page_size = None

        # If an ordering has been specified as a query parameter, save it as the
        # user's preferred ordering for this table.
        if request.user.is_authenticated and self.event:
            if ordering := request.GET.getlist(self.prefixed_order_by_field):
                preferences = request.user.get_event_preferences(self.event)
                preferences.set(f"tables.{self.name}.ordering", ordering, commit=True)

            preferences = request.user.get_event_preferences(self.event)
            columns = preferences.get(f"tables.{self.name}.columns")
            ordering = preferences.get(f"tables.{self.name}.ordering")
            page_size = preferences.get(f"tables.{self.name}.page_size")

        columns = columns or getattr(self, "default_columns", None) or self.Meta.fields
        self._set_columns(columns)

        if ordering is not None:
            self.order_by = ordering

        return page_size


class UnsortableMixin:
    def __init__(self, *args, **kwargs):
        # Prevent ordering of dragsort tables
        kwargs["orderable"] = False
        kwargs["order_by"] = None
        super().__init__(*args, **kwargs)


class FunctionOrderMixin:

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

    def order(self, queryset, is_descending):
        if not self.order_function_lookup:
            return (queryset, False)
        mapped_order_by = []
        for index, field in enumerate(self.order_by):
            if func := self.order_function_lookup.get(field):
                mapped_key = f"sort{index}"
                queryset = queryset.annotate(**{mapped_key: func})
                if is_descending:
                    mapped_key = f"-{mapped_key}"
                    func = func.desc()
                mapped_order_by.append(mapped_key)
            else:
                mapped_order_by.append(field)
        queryset = queryset.order_by(*mapped_order_by)
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
