# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.common.forms.widgets import (
    HtmlDateInput,
    HtmlDateTimeInput,
    MarkdownWidget,
)
from pretalx.common.models.fields import DateField, DateTimeField, MarkdownField

pytestmark = [pytest.mark.unit]


@pytest.mark.parametrize(
    ("field_class", "widget_class"),
    (
        (DateField, HtmlDateInput),
        (DateTimeField, HtmlDateTimeInput),
        (MarkdownField, MarkdownWidget),
    ),
    ids=("date", "datetime", "markdown"),
)
def test_formfield_defaults_widget_but_yields_to_caller(field_class, widget_class):
    field = field_class()

    default = field.formfield()
    overridden = field.formfield(widget=widget_class(attrs={"data-linked": "#other"}))

    assert type(default.widget) is widget_class
    assert overridden.widget.attrs["data-linked"] == "#other"
