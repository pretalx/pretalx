# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django import forms
from django.utils.translation import gettext_lazy as _


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
