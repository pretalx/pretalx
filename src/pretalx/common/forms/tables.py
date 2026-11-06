# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import json

from django import forms

MAX_SORT_LEVELS = 5


def is_numeric_column(column):
    attrs = getattr(getattr(column, "column", column), "attrs", None) or {}
    return "numeric" in str((attrs.get("th") or {}).get("class") or "")


class TablePreferencesForm(forms.Form):
    """Data source for the table options dialog."""

    max_sort_levels = MAX_SORT_LEVELS

    class Media:
        js = [forms.Script("orga/js/ui/dragsort.js", defer="")]
        css = {"all": ["orga/css/ui/dragsort.css"]}

    def __init__(
        self, *args, table=None, export=False, selected=None, ordering=None, **kwargs
    ):
        if not table:
            raise ValueError("No table provided to TablePreferencesForm")

        super().__init__(*args, **kwargs)

        self.table = table
        self.export = export
        self.shown_columns = []
        self.hidden_columns = []
        self.sort_choices = []
        numeric = {}

        canonical = {
            name: order for order, name in enumerate(table.canonical_column_names)
        }

        for name, column in table.columns.items():
            if not self._is_configurable(name, column):
                continue
            entry = {
                "name": name,
                "label": str(column.verbose_name),
                "order": canonical[name],
            }
            shown = name in selected if selected is not None else column.visible
            if shown:
                self.shown_columns.append(entry)
            else:
                self.hidden_columns.append(entry)
            if column.orderable:
                numeric[name] = is_numeric_column(column)
                self.sort_choices.append({**entry, "numeric": numeric[name]})

        if selected is not None:
            position = {name: index for index, name in enumerate(selected)}
            self.shown_columns.sort(key=lambda column: position[column["name"]])
        self.hidden_columns.sort(key=lambda column: column["order"])
        self.sort_choices.sort(key=lambda choice: choice["label"])
        if ordering is None:
            levels = table.current_ordering
        else:
            levels = [
                {
                    "column": field.removeprefix("-"),
                    "direction": "desc" if field.startswith("-") else "asc",
                }
                for field in ordering
            ]
        self.sort_levels = [
            {**level, "numeric": numeric[level["column"]]}
            for level in levels
            if level["column"] in numeric
        ][:MAX_SORT_LEVELS]

        known = {
            column["name"] for column in (*self.shown_columns, *self.hidden_columns)
        }
        defaults = (
            getattr(table, "default_columns", None)
            or getattr(getattr(table, "Meta", None), "fields", None)
            or [column["name"] for column in self.shown_columns]
        )
        self.default_columns = [name for name in defaults if name in known]

    def _is_configurable(self, name, column):
        if name in self.table.exempt_columns:
            return False
        inner = getattr(column, "column", column)
        if self.export:
            exclude = getattr(inner, "exclude_from_export", False)
            return not exclude and name != "code"
        return not getattr(inner, "export_only", False)

    @property
    def default_columns_json(self):
        return json.dumps(self.default_columns)
