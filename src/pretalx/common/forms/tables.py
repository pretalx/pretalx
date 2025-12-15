# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.utils.translation import gettext_lazy as _

from pretalx.common.forms.widgets import EnhancedSelect, ToggleChoiceWidget

DIRECTION_CHOICES = [
    ("asc", _("A–Z / low to high ↑")),
    ("desc", _("Z–A / high to low ↓")),
]


class TablePreferencesForm(forms.Form):
    available_columns = forms.MultipleChoiceField(
        label=_("Available Columns"),
        required=False,
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-control",
                "size": "10",
            }
        ),
    )
    columns = forms.MultipleChoiceField(
        label=_("Selected Columns"),
        required=False,
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-control",
                "size": "10",
            }
        ),
    )
    sort_column_1 = forms.ChoiceField(
        label=_("Sort by"),
        required=False,
        widget=EnhancedSelect(attrs={"data-position": "top"}),
    )
    sort_direction_1 = forms.ChoiceField(
        label=_("Direction"),
        required=False,
        choices=DIRECTION_CHOICES,
        widget=ToggleChoiceWidget(),
    )
    sort_column_2 = forms.ChoiceField(
        label=_("Then by"),
        required=False,
        widget=EnhancedSelect(attrs={"data-position": "top"}),
    )
    sort_direction_2 = forms.ChoiceField(
        label=_("Direction"),
        required=False,
        choices=DIRECTION_CHOICES,
        widget=ToggleChoiceWidget(),
    )

    def __init__(self, *args, table=None, **kwargs):
        if not table:
            raise Exception("No table provided to TablePreferencesForm")

        super().__init__(*args, **kwargs)

        self.table = table
        all_columns = []
        for name, column in table.columns.items():
            if name not in table.exempt_columns:
                all_columns.append((name, str(column.verbose_name)))

        visible = []
        hidden = []
        for name, verbose_name in all_columns:
            if table.columns[name].visible:
                visible.append((name, verbose_name))
            else:
                hidden.append((name, verbose_name))

        self.fields["columns"].choices = visible
        self.fields["columns"].initial = []
        self.fields["available_columns"].choices = sorted(hidden)

        sortable_columns = [("", "---------")] + sorted(
            [
                (name, str(column.verbose_name))
                for name, column in table.columns.items()
                if column.orderable and name not in table.exempt_columns
            ],
            key=lambda x: x[1],
        )

        self.fields["sort_column_1"].choices = sortable_columns
        self.fields["sort_column_2"].choices = sortable_columns

        current_ordering = table.current_ordering
        if current_ordering:
            if len(current_ordering) >= 1:
                self.fields["sort_column_1"].initial = current_ordering[0]["column"]
                self.fields["sort_direction_1"].initial = current_ordering[0][
                    "direction"
                ]
            if len(current_ordering) >= 2:
                self.fields["sort_column_2"].initial = current_ordering[1]["column"]
                self.fields["sort_direction_2"].initial = current_ordering[1][
                    "direction"
                ]
