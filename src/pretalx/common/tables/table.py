# SPDX-FileCopyrightText: 2023-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import django_tables2 as tables
from django.core.exceptions import FieldDoesNotExist
from django.utils.functional import cached_property
from django_tables2.utils import OrderBy, OrderByTuple

from pretalx.common.forms.tables import TablePreferencesForm
from pretalx.common.tables.columns import QuestionColumn
from pretalx.person.models import SpeakerProfile
from pretalx.submission.models import Answer


class QuestionColumnMixin:
    """Mixin for tables that display QuestionColumns with answer caching."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.Meta.model == SpeakerProfile:
            self._question_model = "speaker"
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
                    QuestionColumn(verbose_name=question.question, question=question),
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
        return self._answers_cache.get(record.pk, {}).get(question_id)

    def _get_answer_filter_field(self):
        model = "speaker" if self._question_model == "speaker" else "submission"
        return f"{model}_id__in"

    def _load_all_answers(self):
        try:
            record_ids = [row.record.pk for row in self.rows]
        except (
            AttributeError,
            TypeError,
        ):  # pragma: no cover -- defensive fallback for partially-initialised tables
            record_ids = [record.pk for record in self.data]

        if not record_ids:
            self._answers_cache = {}
            return

        filter_field = self._get_answer_filter_field()
        answers = (
            Answer.objects.filter(
                **{filter_field: record_ids}, question__in=self.short_questions
            )
            .select_related("question")
            .prefetch_related("options")
        )
        self._answers_cache = {}
        cache_key = (
            "speaker_id" if self._question_model == "speaker" else "submission_id"
        )
        for answer in answers:
            answer_key = getattr(answer, cache_key, None)
            self._answers_cache.setdefault(answer_key, {})[answer.question_id] = answer


class BaseTable(tables.Table):
    printable = True

    @property
    def name(self):
        # Needed for HTMX integration. We set it in the base class so that
        # it doesn’t clash with e.g. a ``name`` column. Columns get moved out
        # of the class dict at class creation (via the table metaclass).
        # Hacky hacker noises.
        return self.__class__.__name__


class PretalxTable(BaseTable):
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
            # Don't re-order - just update the display value for sort indicators.
            order_by = value or ()
            order_by = order_by.split(",") if isinstance(order_by, str) else order_by
            valid = []
            for alias in order_by:
                name = OrderBy(alias).bare
                if name in self.columns and self.columns[name].orderable:
                    valid.append(alias)
            # Preserve secondary sort if we only received a primary sort
            if len(valid) == 1 and len(self._order_by) >= 2:
                secondary = self._order_by[1]
                if OrderBy(secondary).bare != OrderBy(valid[0]).bare:
                    valid.append(str(secondary))
            self._order_by = OrderByTuple(valid)
        else:
            # Use parent's setter which includes ordering
            tables.Table.order_by.fset(self, value)

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
            column_name = field.removeprefix("-")
            if column_name in sortable and column_name not in seen_columns:
                valid_ordering.append(field)
                seen_columns.add(column_name)
        return valid_ordering or None

    def _apply_ordering(self, queryset, ordering):
        """Apply multi-column ordering to the queryset, handling function-based columns.

        django_tables2's default ordering mechanism (TableQuerysetData.order_by) has a
        limitation: when a column's order() method returns modified=True, it stops
        processing subsequent columns. This means multi-column sorting doesn't work
        when function-based columns are involved.

        This method applies all ordering ourselves by:
        1. Iterating through all columns in the ordering
        2. For function-based columns (FunctionOrderMixin), applying their annotation
        3. For columns with apply_custom_ordering (like QuestionColumn), using that
        4. For traditional columns, using their accessor
        5. Applying all orderings at once with a single order_by() call

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
            # Check if this column has apply_custom_ordering (e.g., QuestionColumn)
            elif hasattr(column, "apply_custom_ordering"):
                queryset, order_keys = column.apply_custom_ordering(
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
            elif self._is_model_field(column_name):
                order_key = f"-{column_name}" if descending else column_name
                order_by_fields.append(order_key)
            # Skip columns that can't be ordered (e.g., deleted question columns)

        if order_by_fields:
            queryset = queryset.order_by(*order_by_fields)

        return queryset

    def _is_model_field(self, field_name):
        """Check if field_name is a valid model field that can be used for ordering."""
        if not hasattr(self, "Meta") or not hasattr(self.Meta, "model"):
            return False
        try:
            self.Meta.model._meta.get_field(field_name)
        except FieldDoesNotExist:
            return False
        else:
            return True

    def _merge_ordering(self, new_ordering, saved_ordering):
        """Merge new column click ordering with saved multi-column ordering.

        When user clicks a column header, we receive the new primary sort.
        Preserve the secondary sort if present; _validate_ordering will
        handle deduplication if the same column appears in both positions.
        """
        new_ordering = [s for s in (new_ordering or []) if s]
        saved_ordering = [s for s in (saved_ordering or []) if s]
        if not saved_ordering or not new_ordering:
            return new_ordering
        if len(new_ordering) == 2 or len(saved_ordering) == 1:
            return new_ordering
        return [new_ordering[0], saved_ordering[1]]

    def configure(self, request):
        columns = None
        ordering = None
        page_size = None
        # The print view (only ever accessed via HTMX) can override the
        # user’s saved column preferences.
        if request.headers.get("HX-Pretalx-Print"):
            available = set(self.columns.names())
            override_columns = [
                c for c in request.GET.getlist("print") if c and c in available
            ]
        else:
            override_columns = []

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
                # Validate saved ordering in case columns have been removed
                # (e.g., deleted questions)
                ordering = self._validate_ordering(saved_ordering)

            columns = preferences.get(f"tables.{self.name}.columns")
            page_size = preferences.get(f"tables.{self.name}.page_size")

        if override_columns:
            columns = override_columns
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
