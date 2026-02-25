import pytest
from django import forms, template

from pretalx.common.templatetags.form_media import form_media

pytestmark = pytest.mark.unit


def test_form_media_singleton():
    """form_media returns '' on second invocation within the same context."""
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
    """A form with no custom media doesn't trigger base media inclusion."""

    class SimpleForm(forms.Form):
        name = forms.CharField()

    context = template.Context({"form": SimpleForm()})
    result = form_media(context)
    assert str(result) == ""


def test_form_media_with_form_having_media():
    """A form with custom media triggers base media inclusion."""

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
    """Empty formset (no forms) falls back to empty_form media."""

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
    """Context with a list of forms picks up media from the first form."""

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
    """Context with 'extra_forms' key collects media from each form."""

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
    """Without always_base and no forms, no base media is added."""
    context = template.Context({})
    result = form_media(context)
    rendered = str(result)
    assert rendered == ""


def test_form_media_list_with_non_form_items():
    """Lists containing non-form items are ignored."""
    context = template.Context({"items": ["not", "forms"]})
    result = form_media(context)
    assert str(result) == ""


def test_form_media_extra_forms_with_non_form_item():
    """Non-form items in extra_forms list are skipped."""

    class FormA(forms.Form):
        name = forms.CharField()

        class Media:
            js = ["form_a.js"]

    context = template.Context({"extra_forms": [FormA(), "not_a_form"]})
    result = form_media(context)
    rendered = str(result)
    assert "form_a.js" in rendered


def test_form_media_table_media():
    """table_media=True with a table in context adds table media."""

    class FakeTable:
        configuration_form = None

    context = template.Context({"table": FakeTable()})
    result = form_media(context, table_media=True)
    rendered = str(result)
    assert "tables.js" in rendered


def test_form_media_table_media_with_configuration_form():
    """table_media with a configuration_form also includes that form's media."""

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
