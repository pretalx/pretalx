# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django import forms, template

from pretalx.common.forms.widgets import EnhancedSelect
from pretalx.common.templatetags.form_media import form_media

pytestmark = pytest.mark.unit


class SimpleForm(forms.Form):
    name = forms.CharField()


class FormA(forms.Form):
    name = forms.CharField()

    class Media:
        js = ["form_a.js"]


class FormB(forms.Form):
    email = forms.EmailField()

    class Media:
        js = ["form_b.js"]


def test_form_media_renders_base_once():
    context = template.Context({})

    rendered = str(form_media(context, always_base=True))

    assert "base.js" in rendered
    assert "base.css" in rendered
    assert form_media(context) == ""


@pytest.mark.parametrize(
    "context",
    ({}, {"form": SimpleForm()}, {"items": ["not", "forms"]}),
    ids=("empty", "form_without_media", "list_without_forms"),
)
def test_form_media_without_media_renders_nothing(context):
    assert str(form_media(template.Context(context))) == ""


@pytest.mark.parametrize(
    ("context", "scripts"),
    (
        ({"form": FormA()}, ["form_a.js"]),
        ({"my_forms": [FormA(), FormA()]}, ["form_a.js"]),
        ({"extra_forms": [FormA(), FormB()]}, ["form_a.js", "form_b.js"]),
        ({"extra_forms": [FormA(), "not_a_form"]}, ["form_a.js"]),
        ({"my_formset": forms.formset_factory(SimpleForm)()}, ["formsets"]),
        (
            {
                "my_formset": forms.formset_factory(SimpleForm, extra=0)(
                    data={"form-TOTAL_FORMS": "0", "form-INITIAL_FORMS": "0"}
                )
            },
            [],
        ),
    ),
    ids=(
        "form",
        "form_list",
        "extra_forms",
        "extra_forms_with_non_form_item",
        "formset",
        "empty_formset",
    ),
)
def test_form_media_collects_form_media_with_base(context, scripts):
    rendered = str(form_media(template.Context(context)))

    assert "base" in rendered
    for script in scripts:
        assert script in rendered


def test_form_media_extra_js_and_css():
    rendered = str(
        form_media(
            template.Context({}),
            extra_js="custom/script.js",
            extra_css="custom/style.css",
        )
    )

    assert "custom/script.js" in rendered
    assert "custom/style.css" in rendered


def test_form_media_base_js_precedes_dependent_scripts():
    class FormWithSelect(forms.Form):
        choice = forms.ChoiceField(choices=[("a", "a")], widget=EnhancedSelect)

    context = template.Context({"form": FormWithSelect()})
    rendered = str(
        form_media(context, always_base=True, extra_js="common/js/ui/tabs.js")
    )
    base_position = rendered.index("common/js/forms/base.js")
    assert base_position < rendered.index("common/js/ui/tabs.js")
    assert base_position < rendered.index("common/js/forms/select.js")


@pytest.mark.parametrize(
    ("configuration_form", "scripts"),
    ((None, ["tables.js"]), (FormA(), ["tables.js", "form_a.js"])),
    ids=("plain", "with_configuration_form"),
)
def test_form_media_table_media(configuration_form, scripts):
    class FakeTable:
        pass

    table = FakeTable()
    table.configuration_form = configuration_form

    rendered = str(form_media(template.Context({"table": table}), table_media=True))

    for script in scripts:
        assert script in rendered


def test_form_media_with_media_object():
    context = template.Context({"dialog_media": forms.Media(js=["dialog.js"])})
    rendered = str(form_media(context))
    assert "dialog.js" in rendered
