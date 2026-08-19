# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import dataclasses
from dataclasses import dataclass

from django.http import QueryDict
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from pretalx.common.forms.fields import CountableOption
from pretalx.common.forms.widgets import (
    EnhancedSelect,
    EnhancedSelectMultiple,
    SegmentedRadioSelect,
    SelectMultipleWithCount,
)

EMPTY_VALUE = "__none__"
ANY_LABEL = _("Any")

MULTI = "multi"
CHOICE = "choice"
BOOLEAN = "boolean"
SEARCH = "search"
RANGE = "range"


@dataclass(frozen=True)
class FilterChoice:
    value: str
    label: str
    color: str = ""
    count: int = None
    group: str = ""
    css_class: str = ""

    @property
    def css_color(self):
        return css_color(self.color)


@dataclass(frozen=True)
class FilterPill:
    param: str
    value: str
    label: str
    color: str = ""
    remove_url: str = ""
    filter_name: str = ""
    css_class: str = ""

    @property
    def css_color(self):
        return css_color(self.color)

    @property
    def has_own_color(self):
        return bool(self.color) and not self.css_class


def css_color(color):
    if not color:
        return ""
    if color.startswith("--"):
        return f"var({color}, var(--color-neutral))"
    return color


class FilterContext:
    def __init__(self, event=None, user=None, **options):
        self.event = event
        self.user = user
        self.options = options

    def get(self, key, default=None):
        return self.options.get(key, default)


def segmented_widget(label, choices, any_label=None):
    """A tristate-style radio group with an "any" segment in front."""
    widget = SegmentedRadioSelect(
        attrs={"data-empty-value": EMPTY_VALUE}, group_label=label
    )
    widget.choices = [(EMPTY_VALUE, any_label or ANY_LABEL), *choices]
    return widget


class TableFilter:
    control = MULTI
    is_facet = True
    multiple = True
    value = None
    form_id = ""

    def __init__(
        self,
        *,
        name=None,
        param=None,
        label=None,
        field=None,
        section=None,
        with_counts=False,
        distinct=False,
    ):
        self.name = name
        self._param = param
        self._field = field
        self.label = label
        self.section = section
        self.with_counts = with_counts
        self.distinct = distinct
        self.context = FilterContext()

    def get_initial(self):
        return None

    @property
    def param(self):
        return self._param or self.name

    @property
    def field(self):
        return self._field or self.name

    @property
    def event(self):
        return self.context.event

    @property
    def template_name(self):
        control = "range" if self.control == RANGE else "widget"
        return f"common/tables/controls/{control}.html"

    def get_params(self):
        """Every query parameter this filter has."""
        yield self.param

    def render_widget(self, value, form_id=None):
        widget = self.get_widget()
        attrs = {"id": f"id_filter_{self.name}"}
        if form_id:
            attrs["form"] = form_id
        return widget.render(self.param, self.selected_values(value), attrs)

    @property
    def widget_html(self):
        return self.render_widget(self.value, form_id=self.form_id)

    def _colors(self):
        colors = {
            str(choice.value): choice.css_color
            for choice in self.choices
            if choice.color
        }
        if not colors:
            return None
        return lambda value: colors.get(str(value))

    def is_available(self):
        return True

    def selected_values(self, value):
        return [str(value)] if value else []

    def get_choices(self):
        return []

    @cached_property
    def choices(self):
        return list(self.get_choices())

    @cached_property
    def choices_by_value(self):
        return {str(choice.value): choice for choice in self.choices}

    def parse(self, data):
        raise NotImplementedError

    def has_value(self, value):
        return bool(value)

    def is_default(self, value):
        return False

    def filter(self, qs, value):
        return qs

    def get_pills(self, value):
        return []


class ChoiceFilterBase(TableFilter):
    def __init__(self, *, choices=None, min_choices=1, **kwargs):
        super().__init__(**kwargs)
        self._choices = choices
        self.min_choices = min_choices

    def get_choices(self):
        choices = self._choices
        if callable(choices):
            choices = choices(self)
        return [
            choice if isinstance(choice, FilterChoice) else FilterChoice(*choice)
            for choice in (choices or [])
        ]

    def is_available(self):
        return len(self.choices) >= self.min_choices

    def _choice_pill(self, value):
        choice = self.choices_by_value.get(str(value))
        if not choice:
            return None
        return FilterPill(
            param=self.param,
            value=str(value),
            label=choice.label,
            color=choice.color,
            css_class=choice.css_class,
        )


class ModelChoiceMixin:
    def __init__(
        self, *, queryset=None, color_field="color", count_attr=None, **kwargs
    ):
        super().__init__(**kwargs)
        self._queryset = queryset
        self.color_field = color_field
        self.count_attr = count_attr

    def get_queryset(self):
        return self._queryset(self)

    def get_choices(self):
        return [
            FilterChoice(
                value=str(obj.pk),
                label=str(obj),
                color=(getattr(obj, self.color_field, "") or "")
                if self.color_field
                else "",
                count=getattr(obj, self.count_attr, None) if self.count_attr else None,
            )
            for obj in self.get_queryset()
        ]


class MultiChoiceFilter(ChoiceFilterBase):
    control = MULTI

    def get_widget(self):
        attrs = {"title": str(self.label or ""), "data-deferred": "true"}
        if self.with_counts:
            widget = SelectMultipleWithCount(attrs=attrs, color_field=self._colors())
            widget.choices = [
                (choice.value, CountableOption(choice.label, choice.count or 0))
                for choice in self.choices
            ]
        else:
            widget = EnhancedSelectMultiple(attrs=attrs, color_field=self._colors())
            widget.choices = [(choice.value, choice.label) for choice in self.choices]
        return widget

    def parse(self, data):
        return [
            value
            for value in data.getlist(self.param)
            if value in self.choices_by_value
        ]

    def selected_values(self, value):
        return [str(entry) for entry in value or []]

    def filter(self, qs, value):
        qs = qs.filter(**{f"{self.field}__in": value})
        return qs.distinct() if self.distinct else qs

    def get_pills(self, value):
        pills = [self._choice_pill(entry) for entry in value]
        return [pill for pill in pills if pill]


class ModelMultiChoiceFilter(ModelChoiceMixin, MultiChoiceFilter):
    pass


class ChoiceFilter(ChoiceFilterBase):
    control = CHOICE
    multiple = False

    def __init__(self, *, empty_label=None, **kwargs):
        super().__init__(**kwargs)
        self.empty_label = empty_label or _("All")

    def get_widget(self):
        widget = EnhancedSelect(
            attrs={
                "title": str(self.label or ""),
                "data-empty-value": EMPTY_VALUE,
                "data-deferred": "true",
            },
            color_field=self._colors(),
        )
        widget.choices = [(EMPTY_VALUE, self.empty_label), *self._grouped_choices()]
        return widget

    def _grouped_choices(self):
        grouped = []
        for choice in self.choices:
            group = str(choice.group or "")
            if group and grouped and grouped[-1][0] == group:
                grouped[-1][1].append((choice.value, choice.label))
            elif group:
                grouped.append((group, [(choice.value, choice.label)]))
            else:
                grouped.append((choice.value, choice.label))
        return grouped

    def parse(self, data):
        value = data.get(self.param) or ""
        if not value:
            return ""
        return value if value in self.choices_by_value else ""

    def filter(self, qs, value):
        qs = qs.filter(**{self.field: value})
        return qs.distinct() if self.distinct else qs

    def get_pills(self, value):
        pill = self._choice_pill(value)
        return [pill] if pill else []


class SegmentedChoiceFilter(ChoiceFilter):
    """A choice filter shown as a segmented radio group instead of a dropdown.

    Use for 2-3 choices only.
    """

    def get_widget(self):
        return segmented_widget(
            self.label,
            [(choice.value, choice.label) for choice in self.choices],
            any_label=self.empty_label,
        )

    def selected_values(self, value):
        if value and str(value) in self.choices_by_value:
            return [str(value)]
        return [EMPTY_VALUE]

    def get_pills(self, value):
        return [
            dataclasses.replace(pill, label=f"{self.label}: {pill.label}")
            for pill in super().get_pills(value)
        ]


class ModelChoiceFilter(ModelChoiceMixin, ChoiceFilter):
    pass


class BooleanFilter(SegmentedChoiceFilter):
    """The tristate segmented filter for an actual boolean field."""

    control = BOOLEAN

    def __init__(self, *, yes_label=None, no_label=None, any_label=None, **kwargs):
        kwargs.setdefault("empty_label", any_label or ANY_LABEL)
        super().__init__(**kwargs)
        self.yes_label = yes_label or _("Yes")
        self.no_label = no_label or _("No")

    def get_choices(self):
        return [
            FilterChoice("true", self.yes_label),
            FilterChoice("false", self.no_label),
        ]

    def parse(self, data):
        value = data.get(self.param)
        if value in ("true", "1", "on", "yes"):
            return True
        if value in ("false", "0", "off", "no"):
            return False
        return None

    def has_value(self, value):
        return value is not None

    def selected_values(self, value):
        if value is None:
            return [EMPTY_VALUE]
        return ["true" if value else "false"]

    def filter(self, qs, value):
        return qs.filter(**{self.field: value})

    def get_pills(self, value):
        return super().get_pills("true" if value else "false")


class SearchFilter(TableFilter):
    control = SEARCH
    is_facet = False
    multiple = False

    def __init__(self, *, search=None, fulltext=False, fulltext_label=None, **kwargs):
        kwargs.setdefault("param", "q")
        kwargs.setdefault("name", "search")
        super().__init__(**kwargs)
        self._search = search
        self.has_fulltext = fulltext
        self.fulltext_label = fulltext_label or _("Search full text")

    def get_params(self):
        yield self.param
        if self.has_fulltext:
            yield "fulltext"

    def parse(self, data):
        query = (data.get(self.param) or "").strip()
        fulltext = bool(self.has_fulltext and data.get("fulltext"))
        return {"query": query, "fulltext": fulltext}

    def has_value(self, value):
        return bool(value["query"])

    def filter(self, qs, value):
        return self._search(
            qs, value["query"], fulltext=value["fulltext"], context=self.context
        )


class TableFilterSet:
    def __init__(self, filters, data=None, context=None, form_id=""):
        self.context = context or FilterContext()
        self.form_id = form_id
        self.data = QueryDict() if data is None else data
        self.filters = {}
        for table_filter in filters:
            table_filter.context = self.context
            table_filter.form_id = form_id
            self.filters[table_filter.name] = table_filter
        self._base_qs = None
        self._filtered_qs = None

    @property
    def param_names(self):
        return sorted(
            {
                param
                for table_filter in self.filters.values()
                for param in table_filter.get_params()
            }
        )

    def _has_any_param(self):
        return any(param in self.data for param in self.param_names)

    def _apply_initials(self):
        initials = {
            table_filter.param: table_filter.get_initial()
            for table_filter in self.filters.values()
            if table_filter.get_initial() is not None
        }
        if not initials:
            return
        data = self.data.copy()
        for param, value in initials.items():
            if isinstance(value, (list, tuple, set, frozenset)):
                data.setlist(param, [str(entry) for entry in value])
            else:
                data[param] = str(value)
        self.data = data

    @cached_property
    def values(self):
        if not self._has_any_param():
            self._apply_initials()
        values = {}
        for name, table_filter in self.filters.items():
            data = self.data
            # We check availability lazy on demand, otherwise we would
            # eval filter choices unnecessarily, which can include expensive
            # query counts.
            if (
                any(param in data for param in table_filter.get_params())
                and not table_filter.is_available()
            ):
                data = QueryDict()
            values[name] = table_filter.value = table_filter.parse(data)
        return values

    @cached_property
    def facets(self):
        self.values  # noqa: B018
        return [f for f in self.filters.values() if f.is_facet and f.is_available()]

    @property
    def search(self):
        for table_filter in self.filters.values():
            if table_filter.control == SEARCH:
                return table_filter

    @property
    def search_value(self):
        search = self.search
        return self.values[search.name] if search else {"query": "", "fulltext": False}

    def is_set(self, name):
        table_filter = self.filters.get(name)
        if not table_filter:
            return False
        value = self.values[name]
        return table_filter.has_value(value) and not table_filter.is_default(value)

    def filter(self, qs):
        self._base_qs = qs
        for name, table_filter in self.filters.items():
            value = self.values[name]
            if table_filter.has_value(value):
                qs = table_filter.filter(qs, value)
        self._filtered_qs = qs
        return qs

    @property
    def is_active(self):
        return any(self.is_set(name) for name in self.filters)

    @cached_property
    def pills(self):
        pills = []
        for name, table_filter in self.filters.items():
            if not table_filter.is_facet or not self.is_set(name):
                continue
            pills.extend(
                dataclasses.replace(
                    pill,
                    remove_url=self.remove_url(table_filter, pill.value),
                    filter_name=name,
                )
                for pill in table_filter.get_pills(self.values[name])
            )
        return pills

    def _clean_query(self):
        self.values  # noqa: B018
        query = self.data.copy()
        query.pop("page", None)
        return query

    def remove_url(self, table_filter, value):
        query = self._clean_query()
        if table_filter.multiple:
            remaining = [
                entry for entry in query.getlist(table_filter.param) if entry != value
            ]
            query.setlist(table_filter.param, remaining)
        else:
            query.pop(table_filter.param, None)
        return f"?{query.urlencode()}"

    @property
    def clear_url(self):
        query = self._clean_query()
        for table_filter in self.filters.values():
            for param in table_filter.get_params():
                query.pop(param, None)
        return f"?{query.urlencode()}"

    @cached_property
    def filtered_count(self):
        if self._filtered_qs is None:
            return 0
        return self._filtered_qs.count()

    @cached_property
    def total_count(self):
        if not self.is_active or self._base_qs is None:
            return None
        return self._base_qs.count()
