# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django import forms

from pretalx.common.templatetags.form_errors import fields_with_errors, form_errors

pytestmark = pytest.mark.unit


class ErrorForm(forms.Form):
    visible = forms.CharField()
    optional = forms.CharField(required=False)
    hidden = forms.CharField(widget=forms.HiddenInput())


@pytest.mark.parametrize(
    ("data", "expected"),
    (({}, ["visible"]), ({"visible": "a", "hidden": "b"}, [])),
    ids=["rejected", "valid"],
)
def test_fields_with_errors_returns_only_rejected_visible_fields(data, expected):
    form = ErrorForm(data=data)

    assert [field.name for field in fields_with_errors(form)] == expected


class NonFieldErrorForm(ErrorForm):
    def clean(self):
        raise forms.ValidationError("nope")


def test_fields_with_errors_tolerates_missing_form():
    assert fields_with_errors(None) == []
    assert fields_with_errors("") == []


def test_form_errors_aggregates_forms_and_marks_them():
    form = ErrorForm(data={})
    other = NonFieldErrorForm(data={"visible": "a", "hidden": "b"})

    context = form_errors(form, [other, None])

    assert [field.name for field in context["field_errors"]] == ["visible"]
    assert context["errors"] == ["nope"]
    assert context["generic"] is False
    assert form.error_summary_rendered
    assert other.error_summary_rendered


def test_form_errors_skips_forms_covered_by_earlier_summary():
    form = NonFieldErrorForm(data={"visible": "a", "hidden": "b"})

    assert form_errors(form)["errors"] == ["nope"]
    context = form_errors(form, fields=False)

    assert context["errors"] == []
    assert context["generic"] is False


def test_form_errors_without_fields_reports_only_non_field_errors():
    form = ErrorForm(data={})

    context = form_errors(form, fields=False)

    assert context["field_errors"] == []
    assert context["errors"] == []
    assert context["generic"] is False


def test_form_errors_hidden_field_errors_fall_back_to_generic_message():
    form = ErrorForm(data={"visible": "a"})

    context = form_errors(form)

    assert context["field_errors"] == []
    assert context["errors"] == []
    assert context["generic"] is True
