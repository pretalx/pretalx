# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import zoneinfo

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

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


def test_datetime_formfield_rejects_value_outside_utc_range():
    formfield = DateTimeField().formfield()

    with (
        timezone.override(zoneinfo.ZoneInfo("Europe/Berlin")),
        pytest.raises(ValidationError) as excinfo,
    ):
        formfield.clean("0001-01-01T00:00")

    assert excinfo.value.code == "invalid"
