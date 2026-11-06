# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.http import QueryDict
from django.utils.translation import gettext_lazy as _

from pretalx.common.forms.tables import TablePreferencesForm
from pretalx.common.forms.widgets import SegmentedRadioSelect
from pretalx.common.models.exports import TableExport
from pretalx.common.tables.export import (
    build_filterset,
    filters_to_querydict,
    get_table_serializers,
)


class TableExportForm(forms.ModelForm):
    class Meta:
        model = TableExport
        fields = ("name", "serializer")

    def __init__(
        self,
        *args,
        event,
        user,
        table_class,
        table=None,
        require_name=False,
        can_save=False,
        form_id="",
        **kwargs,
    ):
        self.event = event
        self.user = user
        self.table_class = table_class
        super().__init__(*args, **kwargs)
        if not require_name and can_save:
            self.fields["save"] = forms.BooleanField(
                label=_("Save export"),
                required=False,
                help_text=_(
                    "You can re-run a saved export to download current data in the same format."
                ),
            )
        saving = "save" in self.fields and (
            self.is_bound
            and self.fields["save"].widget.value_from_datadict(
                self.data, self.files, self.add_prefix("save")
            )
        )
        self.fields["name"].required = require_name or not self.is_bound or saving
        self.serializers = get_table_serializers(event)
        self.fields["serializer"] = forms.ChoiceField(
            label=_("Export format"),
            choices=[
                (identifier, serializer.verbose_name)
                for identifier, serializer in self.serializers.items()
            ],
            widget=SegmentedRadioSelect,
            initial=self.instance.serializer or "csv",
        )
        posted_serializer = self.fields["serializer"].widget.value_from_datadict(
            self.data, self.files, self.add_prefix("serializer")
        )
        self.option_field_names = []
        options = self.instance.serializer_options or {}
        for serializer in self.serializers.values():
            for name, field in serializer.option_fields(event).items():
                saved = options.get(name)
                if saved is not None and (
                    not isinstance(field, forms.ChoiceField) or field.valid_value(saved)
                ):
                    field.initial = saved
                if self.is_bound and serializer.identifier != posted_serializer:
                    field.required = False
                field_name = f"{serializer.identifier}_{name}"
                self.fields[field_name] = field
                self.option_field_names.append((serializer.identifier, field_name))

        self.live_table = table is not None
        self.table = table or self._build_table()
        self.from_list_url = self.is_bound and "filters" in self.data
        self.fresh_config = not self.is_bound and not self.instance.pk
        self.filter_data = self._get_filter_data()
        # The toolbar dialog renders no filter widgets, so an unbound form
        # for a live table skips building the (query-heavy) filterset.
        self.filterset = None
        if table is None or self.is_bound:
            self.filterset = build_filterset(
                table_class, event, user, {}, form_id=form_id
            )
        if self.filterset:
            self.filterset.data = self.filter_data
            self.filterset.apply_initials = self.from_list_url or self.fresh_config
        self.columns = self._get_columns()
        self.ordering = self._get_ordering()
        self.columns_form = TablePreferencesForm(
            table=self.table, export=True, selected=self.columns, ordering=self.ordering
        )

    @property
    def option_bound_fields(self):
        return [
            (identifier, self[name]) for identifier, name in self.option_field_names
        ]

    def _build_table(self):
        queryset = self.table_class.base_queryset(self.event, self.user).none()
        return self.table_class(
            data=queryset, event=self.event, user=self.user, for_export=True
        )

    def _get_filter_data(self):
        if not self.is_bound:
            return filters_to_querydict(self.instance.filters)
        if self.from_list_url:
            return QueryDict(self.data["filters"].lstrip("?"))
        return self.data

    @property
    def preferences(self):
        if not self.user or not self.user.pk:
            return None
        return self.user.get_event_preferences(self.event)

    def _get_columns(self):
        if self.is_bound and "columns" in self.data:
            columns = self.data.getlist("columns")
        elif self.instance.pk:
            columns = list(self.instance.columns or [])
        elif self.live_table:
            columns = [
                name for name, column in self.table.columns.items() if column.visible
            ]
        elif self.preferences:
            columns = self.preferences.get(f"tables.{self.table.name}.columns") or []
        else:
            columns = []
        if not columns:
            columns = self.table.default_export_columns
        offered = {
            name
            for name, column in self.table.columns.items()
            if name not in self.table.exempt_columns
            and not column.column.exclude_from_export
            and name != "code"
        }
        return [name for name in columns if name in offered]

    def _get_ordering(self):
        saved = None
        if self.is_bound and "ordering" in self.data:
            ordering = self.data.getlist("ordering")
        elif self.from_list_url:
            # Get ordering from passed querystring
            if self.preferences:
                saved = self.preferences.get(f"tables.{self.table.name}.ordering")
            ordering = (
                self.filter_data.getlist(self.table.prefixed_order_by_field) or saved
            )
        else:
            ordering = list(self.instance.ordering or [])
        return self.table.resolve_ordering(ordering, saved)

    @property
    def filters(self):
        if not self.filterset:
            return {}
        return self.filterset.resolved_params()

    @property
    def serializer_options(self):
        serializer = self.cleaned_data.get("serializer")
        return {
            name.removeprefix(f"{identifier}_"): self.cleaned_data.get(name)
            for identifier, name in self.option_field_names
            if identifier == serializer
        }

    def save(self, commit=True):
        self.instance.event = self.event
        self.instance.table = self.table_class.__name__
        self.instance.columns = self.columns
        self.instance.ordering = self.ordering
        self.instance.filters = self.filters
        self.instance.serializer_options = self.serializer_options
        return super().save(commit=commit)
