# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django import forms, template

from pretalx.common.forms.widgets import EnhancedSelect
from pretalx.common.templatetags.form_media import form_media

pytestmark = pytest.mark.unit


def test_form_media_singleton():
    context = template.Context({})
    form_media(context, always_base=True)
    assert form_media(context) == ""


def test_form_media_always_base():
    context = template.Context({})
    result = form_media(context, always_base=True)
    rendered = str(result)
    assert "base.js" in rendered
    assert "base.css" in rendered


def test_form_media_with_form_no_custom_media():
    class SimpleForm(forms.Form):
        name = forms.CharField()

    context = template.Context({"form": SimpleForm()})
    result = form_media(context)
    assert str(result) == ""


def test_form_media_with_form_having_media():
    class FormWithMedia(forms.Form):
        name = forms.CharField()

        class Media:
            js = ["custom/widget.js"]

    context = template.Context({"form": FormWithMedia()})
    result = form_media(context)
    rendered = str(result)
    assert "base" in rendered
    assert "custom/widget.js" in rendered


def test_form_media_with_formset():
    class SimpleForm(forms.Form):
        name = forms.CharField()

    simple_formset_cls = forms.formset_factory(SimpleForm)
    formset = simple_formset_cls()
    context = template.Context({"my_formset": formset})
    result = form_media(context)
    rendered = str(result)
    assert "base" in rendered
    assert "formsets" in rendered


def test_form_media_with_empty_formset():
    class SimpleForm(forms.Form):
        name = forms.CharField()

    simple_formset_cls = forms.formset_factory(SimpleForm, extra=0)
    formset = simple_formset_cls(
        data={"form-TOTAL_FORMS": "0", "form-INITIAL_FORMS": "0"}
    )
    context = template.Context({"my_formset": formset})
    result = form_media(context)
    rendered = str(result)
    assert "base" in rendered


def test_form_media_extra_js():
    context = template.Context({})
    result = form_media(context, extra_js="custom/script.js")
    rendered = str(result)
    assert "custom/script.js" in rendered


def test_form_media_extra_css():
    context = template.Context({})
    result = form_media(context, extra_css="custom/style.css")
    rendered = str(result)
    assert "custom/style.css" in rendered


def test_form_media_with_form_list():
    class FormWithMedia(forms.Form):
        name = forms.CharField()

        class Media:
            js = ["custom/widget.js"]

    context = template.Context({"my_forms": [FormWithMedia(), FormWithMedia()]})
    result = form_media(context)
    rendered = str(result)
    assert "base" in rendered
    assert "custom/widget.js" in rendered


def test_form_media_extra_forms():
    class FormA(forms.Form):
        name = forms.CharField()

        class Media:
            js = ["form_a.js"]

    class FormB(forms.Form):
        email = forms.EmailField()

        class Media:
            js = ["form_b.js"]

    context = template.Context({"extra_forms": [FormA(), FormB()]})
    result = form_media(context)
    rendered = str(result)
    assert "base" in rendered
    assert "form_a.js" in rendered
    assert "form_b.js" in rendered


def test_form_media_empty_context_no_base():
    context = template.Context({})
    result = form_media(context)
    rendered = str(result)
    assert rendered == ""


def test_form_media_list_with_non_form_items():
    context = template.Context({"items": ["not", "forms"]})
    result = form_media(context)
    assert str(result) == ""


def test_form_media_extra_forms_with_non_form_item():
    class FormA(forms.Form):
        name = forms.CharField()

        class Media:
            js = ["form_a.js"]

    context = template.Context({"extra_forms": [FormA(), "not_a_form"]})
    result = form_media(context)
    rendered = str(result)
    assert "form_a.js" in rendered


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


def test_form_media_table_media():
    class FakeTable:
        configuration_form = None

    context = template.Context({"table": FakeTable()})
    result = form_media(context, table_media=True)
    rendered = str(result)
    assert "tables.js" in rendered


def test_form_media_table_media_with_configuration_form():
    class ConfigForm(forms.Form):
        cols = forms.CharField()

        class Media:
            js = ["config.js"]

    class FakeTable:
        configuration_form = ConfigForm()

    context = template.Context({"table": FakeTable()})
    result = form_media(context, table_media=True)
    rendered = str(result)
    assert "tables.js" in rendered
    assert "config.js" in rendered
