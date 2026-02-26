import pytest
from django import forms

from pretalx.cfp.forms.cfp import CfPFormMixin

pytestmark = pytest.mark.unit


class _TestForm(CfPFormMixin, forms.Form):
    """A minimal form using CfPFormMixin for testing."""

    title = forms.CharField()
    abstract = forms.CharField(required=False)
    description = forms.CharField(required=False)


def test_cfp_form_mixin_init_without_field_configuration():
    form = _TestForm()

    assert form.field_configuration is None
    assert list(form.fields.keys()) == ["title", "abstract", "description"]


def test_cfp_form_mixin_init_stores_field_configuration_as_dict():
    config = [{"key": "title"}, {"key": "abstract"}]

    form = _TestForm(field_configuration=config)

    assert isinstance(form.field_configuration, dict)
    assert set(form.field_configuration.keys()) == {"title", "abstract"}


def test_cfp_form_mixin_reorder_fields():
    config = [{"key": "description"}, {"key": "abstract"}, {"key": "title"}]

    form = _TestForm(field_configuration=config)

    assert list(form.fields.keys()) == ["description", "abstract", "title"]


def test_cfp_form_mixin_reorder_fields_preserves_unconfigured_fields():
    """Fields not in the config are appended after the configured ones."""
    config = [{"key": "abstract"}]

    form = _TestForm(field_configuration=config)

    keys = list(form.fields.keys())
    assert keys[0] == "abstract"
    assert set(keys[1:]) == {"title", "description"}


def test_cfp_form_mixin_reorder_fields_ignores_unknown_keys():
    """Keys in the config that don't match form fields are silently skipped."""
    config = [{"key": "nonexistent"}, {"key": "title"}]

    form = _TestForm(field_configuration=config)

    assert list(form.fields.keys()) == ["title", "abstract", "description"]


def test_cfp_form_mixin_update_cfp_texts_sets_label():
    config = [{"key": "title", "label": "Custom Title"}]

    form = _TestForm(field_configuration=config)

    assert form.fields["title"].label == "Custom Title"


def test_cfp_form_mixin_update_cfp_texts_sets_help_text():
    config = [{"key": "title", "help_text": "Enter a descriptive title"}]

    form = _TestForm(field_configuration=config)

    assert form.fields["title"].original_help_text == "Enter a descriptive title"
    assert form.fields["title"].help_text  # rendered via rich_text


def test_cfp_form_mixin_update_cfp_texts_no_help_text():
    """When help_text is empty/missing, original_help_text is set to empty string."""
    config = [{"key": "title"}]

    form = _TestForm(field_configuration=config)

    assert form.fields["title"].original_help_text == ""


def test_cfp_form_mixin_update_cfp_texts_preserves_added_help_text():
    """If a field has an added_help_text attribute (set by a downstream mixin
    before CfPFormMixin processes the config), it's appended to help_text."""

    class _AddedHelpMixin:
        """Simulates a downstream mixin that sets added_help_text during init."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields["title"].added_help_text = "(max 100 chars)"

    class _FormWithAddedHelp(CfPFormMixin, _AddedHelpMixin, forms.Form):
        title = forms.CharField()

    config = [{"key": "title", "help_text": "Be descriptive"}]
    form = _FormWithAddedHelp(field_configuration=config)

    help_html = str(form.fields["title"].help_text)
    assert "(max 100 chars)" in help_html


def test_cfp_form_mixin_update_cfp_texts_does_not_set_label_when_missing():
    config = [{"key": "title", "help_text": "Some help"}]

    form = _TestForm(field_configuration=config)

    # Label is not overwritten — stays as the default (None for CharField)
    assert form.fields["title"].label is None


def test_cfp_form_mixin_update_cfp_texts_skips_missing_field():
    """_update_cfp_texts returns early when field_name is not in self.fields."""
    config = [{"key": "title"}]
    form = _TestForm(field_configuration=config)

    # Calling _update_cfp_texts on a nonexistent field doesn't raise
    form._update_cfp_texts("nonexistent")


def test_cfp_form_mixin_update_cfp_texts_skips_when_no_field_configuration():
    """_update_cfp_texts returns early when field_configuration is falsy."""
    form = _TestForm()
    form._update_cfp_texts("title")

    # No original_help_text was set since field_configuration is None
    assert not hasattr(form.fields["title"], "original_help_text")


def test_cfp_form_mixin_update_cfp_texts_sets_label_and_help_text_together():
    config = [{"key": "title", "label": "Talk Title", "help_text": "Max 100 chars"}]

    form = _TestForm(field_configuration=config)

    assert form.fields["title"].label == "Talk Title"
    assert form.fields["title"].original_help_text == "Max 100 chars"
