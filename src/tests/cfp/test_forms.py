# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django import forms

from pretalx.cfp.forms import CfPFormMixin, RequestRequire
from tests.factories import EventFactory

pytestmark = pytest.mark.unit


class _CfPMixinForm(CfPFormMixin, forms.Form):
    """A minimal form using CfPFormMixin for testing."""

    title = forms.CharField()
    abstract = forms.CharField(required=False)
    description = forms.CharField(required=False)


class RequestRequireTestForm(RequestRequire, forms.Form):
    title = forms.CharField()
    abstract = forms.CharField(widget=forms.Textarea)

    def __init__(self, *args, event=None, **kwargs):
        self.event = event
        super().__init__(*args, **kwargs)

    class Meta:
        request_require = ["title", "abstract"]


class RequestRequireWithTagsForm(RequestRequire, forms.Form):
    title = forms.CharField()
    tags = forms.MultipleChoiceField(
        choices=[("a", "A"), ("b", "B"), ("c", "C")], required=False
    )

    def __init__(self, *args, event=None, **kwargs):
        self.event = event
        super().__init__(*args, **kwargs)

    class Meta:
        request_require = ["title"]


def test_cfp_form_mixin_init_without_field_configuration():
    form = _CfPMixinForm()

    assert form.field_configuration is None
    assert list(form.fields.keys()) == ["title", "abstract", "description"]


def test_cfp_form_mixin_init_stores_field_configuration_as_dict():
    config = [{"key": "title"}, {"key": "abstract"}]

    form = _CfPMixinForm(field_configuration=config)

    assert isinstance(form.field_configuration, dict)
    assert set(form.field_configuration.keys()) == {"title", "abstract"}


def test_cfp_form_mixin_reorder_fields():
    config = [{"key": "description"}, {"key": "abstract"}, {"key": "title"}]

    form = _CfPMixinForm(field_configuration=config)

    assert list(form.fields.keys()) == ["description", "abstract", "title"]


def test_cfp_form_mixin_reorder_fields_preserves_unconfigured_fields():
    """Fields not in the config are appended after the configured ones."""
    config = [{"key": "abstract"}]

    form = _CfPMixinForm(field_configuration=config)

    keys = list(form.fields.keys())
    assert keys[0] == "abstract"
    assert set(keys[1:]) == {"title", "description"}


def test_cfp_form_mixin_reorder_fields_ignores_unknown_keys():
    """Keys in the config that don't match form fields are silently skipped."""
    config = [{"key": "nonexistent"}, {"key": "title"}]

    form = _CfPMixinForm(field_configuration=config)

    assert list(form.fields.keys()) == ["title", "abstract", "description"]


def test_cfp_form_mixin_update_cfp_texts_sets_label():
    config = [{"key": "title", "label": "Custom Title"}]

    form = _CfPMixinForm(field_configuration=config)

    assert form.fields["title"].label == "Custom Title"


def test_cfp_form_mixin_update_cfp_texts_sets_help_text():
    config = [{"key": "title", "help_text": "Enter a descriptive title"}]

    form = _CfPMixinForm(field_configuration=config)

    assert form.fields["title"].original_help_text == "Enter a descriptive title"
    assert form.fields["title"].help_text  # rendered via rich_text


def test_cfp_form_mixin_update_cfp_texts_no_help_text():
    """When help_text is empty/missing, original_help_text is set to empty string."""
    config = [{"key": "title"}]

    form = _CfPMixinForm(field_configuration=config)

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

    form = _CfPMixinForm(field_configuration=config)

    # Label is not overwritten — stays as the default (None for CharField)
    assert form.fields["title"].label is None


def test_cfp_form_mixin_update_cfp_texts_skips_missing_field():
    config = [{"key": "title"}]
    form = _CfPMixinForm(field_configuration=config)

    # Calling _update_cfp_texts on a nonexistent field doesn't raise
    form._update_cfp_texts("nonexistent")


def test_cfp_form_mixin_update_cfp_texts_skips_when_no_field_configuration():
    form = _CfPMixinForm()
    form._update_cfp_texts("title")

    # No original_help_text was set since field_configuration is None
    assert not hasattr(form.fields["title"], "original_help_text")


def test_cfp_form_mixin_update_cfp_texts_sets_label_and_help_text_together():
    config = [{"key": "title", "label": "Talk Title", "help_text": "Max 100 chars"}]

    form = _CfPMixinForm(field_configuration=config)

    assert form.fields["title"].label == "Talk Title"
    assert form.fields["title"].original_help_text == "Max 100 chars"


@pytest.mark.parametrize(
    ("text", "min_length", "max_length", "count_in", "expected"),
    (
        ("existing", None, None, "chars", "existing"),
        ("t", 1, 3, "chars", "t Please write between 1 and 3 characters."),
        ("", 1, 3, "chars", "Please write between 1 and 3 characters."),
        ("t", 0, 3, "chars", "t Please write at most 3 characters."),
        ("t", 1, 0, "chars", "t Please write at least 1 characters."),
        ("t", 1, 3, "words", "t Please write between 1 and 3 words."),
        ("", 1, 3, "words", "Please write between 1 and 3 words."),
        ("t", 0, 3, "words", "t Please write at most 3 words."),
        ("t", 1, 0, "words", "t Please write at least 1 words."),
    ),
)
def test_request_require_get_help_text(
    text, min_length, max_length, count_in, expected
):
    assert (
        RequestRequire.get_help_text(text, min_length, max_length, count_in) == expected
    )


@pytest.mark.parametrize(
    ("value", "min_length", "max_length", "count_in"),
    (
        ("word word word", None, None, "chars"),
        ("word word word", None, None, "words"),
        ("hello world", 1, 100, "chars"),
        ("hello world", 1, 100, "words"),
        ("a" * 50, 10, 100, "chars"),
        ("one two three", 1, 3, "words"),
        ("word word word", None, 300, "chars"),
        ("word word word", None, 3, "words"),
    ),
    ids=(
        "no_constraints_chars",
        "no_constraints_words",
        "chars_in_range",
        "words_in_range",
        "chars_mid_range",
        "words_at_boundary",
        "chars_well_under_max",
        "words_at_max_boundary",
    ),
)
def test_request_require_validate_field_length_accepts_valid(
    value, min_length, max_length, count_in
):
    RequestRequire.validate_field_length(value, min_length, max_length, count_in)


@pytest.mark.parametrize(
    ("value", "min_length", "max_length", "count_in"),
    (
        ("hi", 10, 100, "chars"),
        ("a" * 200, 10, 100, "chars"),
        ("one", 5, None, "words"),
        ("one two three four five six", None, 3, "words"),
    ),
    ids=("chars_too_short", "chars_too_long", "words_too_few", "words_too_many"),
)
def test_request_require_validate_field_length_rejects_invalid(
    value, min_length, max_length, count_in
):
    with pytest.raises(forms.ValidationError):
        RequestRequire.validate_field_length(value, min_length, max_length, count_in)


def test_request_require_validate_field_length_counts_crlf_as_one_char():
    value = "line1\r\nline2"
    RequestRequire.validate_field_length(value, 11, 11, "chars")


def test_request_require_validate_field_length_word_count():
    value = "one two three"
    RequestRequire.validate_field_length(value, 3, 3, "words")


@pytest.mark.parametrize(
    ("text", "min_number", "max_number", "expected"),
    (
        ("existing", None, None, "existing"),
        ("", 2, 5, "Please select between 2 and 5 tags."),
        ("", 3, 3, "Please select exactly 3 tags."),
        ("", 2, None, "Please select at least 2 tags."),
        ("", None, 5, "Please select at most 5 tags."),
        ("Base.", 1, 3, "Base. Please select between 1 and 3 tags."),
    ),
    ids=("no_limits", "min_max", "exact", "min_only", "max_only", "prepends_existing"),
)
def test_request_require_get_tag_help_text(text, min_number, max_number, expected):
    assert RequestRequire.get_tag_help_text(text, min_number, max_number) == expected


@pytest.mark.parametrize(
    ("value", "min_number", "max_number"),
    ((["a", "b"], 1, 5), (["a", "b", "c"], 3, 3), ([], None, 5)),
    ids=("in_range", "exact", "empty_under_max"),
)
def test_request_require_validate_tag_count_accepts_valid(
    value, min_number, max_number
):
    RequestRequire.validate_tag_count(value, min_number, max_number)


@pytest.mark.parametrize(
    ("value", "min_number", "max_number"),
    ((["a"], 3, 5), (["a", "b", "c", "d", "e", "f"], None, 3), (None, 2, None)),
    ids=("too_few", "too_many", "none_below_min"),
)
def test_request_require_validate_tag_count_rejects_invalid(
    value, min_number, max_number
):
    with pytest.raises(forms.ValidationError):
        RequestRequire.validate_tag_count(value, min_number, max_number)


@pytest.mark.django_db
def test_request_require_init_sets_field_required_from_cfp():
    event = EventFactory(
        cfp__fields={
            "title": {"visibility": "required", "min_length": None, "max_length": None},
            "abstract": {
                "visibility": "optional",
                "min_length": None,
                "max_length": None,
            },
        }
    )

    form = RequestRequireTestForm(event=event)

    assert form.fields["title"].required is True
    assert form.fields["abstract"].required is False


@pytest.mark.django_db
def test_request_require_init_removes_do_not_ask_fields():
    event = EventFactory(
        cfp__fields={
            "title": {
                "visibility": "do_not_ask",
                "min_length": None,
                "max_length": None,
            },
            "abstract": {
                "visibility": "required",
                "min_length": None,
                "max_length": None,
            },
        }
    )

    form = RequestRequireTestForm(event=event)

    assert "title" not in form.fields
    assert "abstract" in form.fields


@pytest.mark.django_db
def test_request_require_init_adds_length_validator_with_chars():
    event = EventFactory(
        cfp__fields={
            "title": {"visibility": "required", "min_length": 5, "max_length": 100}
        }
    )

    form = RequestRequireTestForm(event=event)

    field = form.fields["title"]
    assert field.widget.attrs["data-minlength"] == 5
    assert field.widget.attrs["data-maxlength"] == 100


@pytest.mark.django_db
def test_request_require_init_word_counting_skips_data_attrs():
    event = EventFactory(
        cfp__fields={
            "title": {"visibility": "required", "min_length": 5, "max_length": 100}
        },
        cfp__settings={"count_length_in": "words"},
    )

    form = RequestRequireTestForm(event=event)

    field = form.fields["title"]
    assert "data-minlength" not in field.widget.attrs
    assert "data-maxlength" not in field.widget.attrs


@pytest.mark.django_db
def test_request_require_init_adds_help_text_for_length():
    event = EventFactory(
        cfp__fields={
            "title": {"visibility": "required", "min_length": 10, "max_length": 200}
        }
    )

    form = RequestRequireTestForm(event=event)

    assert (
        form.fields["title"].help_text == " Please write between 10 and 200 characters."
    )


@pytest.mark.django_db
def test_request_require_init_field_not_in_form_is_skipped():
    """When a request_require key has visibility != do_not_ask but the form
    doesn't define that field, the walrus operator yields None and the
    loop continues without error."""

    class FormWithoutDescription(RequestRequire, forms.Form):
        title = forms.CharField()

        def __init__(self, *args, event=None, **kwargs):
            self.event = event
            super().__init__(*args, **kwargs)

        class Meta:
            # 'description' is a valid default_fields key but form lacks it
            request_require = ["title", "description"]

    event = EventFactory(
        cfp__fields={
            "title": {"visibility": "required", "min_length": None, "max_length": None},
            "description": {
                "visibility": "optional",
                "min_length": None,
                "max_length": None,
            },
        }
    )

    form = FormWithoutDescription(event=event)

    assert "title" in form.fields
    assert "description" not in form.fields


@pytest.mark.django_db
def test_request_require_init_tags_with_limits():
    event = EventFactory(
        cfp__fields={
            "title": {"visibility": "required", "min_length": None, "max_length": None},
            "tags": {"visibility": "optional", "min": 1, "max": 5},
        }
    )

    form = RequestRequireWithTagsForm(event=event)

    field = form.fields["tags"]
    assert field.help_text == "Please select between 1 and 5 tags."


@pytest.mark.django_db
def test_request_require_init_tags_without_limits_preserves_help_text():
    event = EventFactory(
        cfp__fields={
            "title": {"visibility": "required", "min_length": None, "max_length": None},
            "tags": {"visibility": "optional", "min": None, "max": None},
        }
    )

    class TagsWithHelpForm(RequestRequire, forms.Form):
        title = forms.CharField()
        tags = forms.MultipleChoiceField(
            choices=[("a", "A")], required=False, help_text="Choose tags."
        )

        def __init__(self, *args, event=None, **kwargs):
            self.event = event
            super().__init__(*args, **kwargs)

        class Meta:
            request_require = ["title"]

    form = TagsWithHelpForm(event=event)

    assert form.fields["tags"].help_text == "Choose tags."


@pytest.mark.django_db
def test_request_require_init_tags_without_limits_or_help_text():
    event = EventFactory(
        cfp__fields={
            "title": {"visibility": "required", "min_length": None, "max_length": None},
            "tags": {"visibility": "optional", "min": None, "max": None},
        }
    )

    form = RequestRequireWithTagsForm(event=event)

    assert not form.fields["tags"].help_text


@pytest.mark.django_db
def test_request_require_init_min_only_chars():
    event = EventFactory(
        cfp__fields={
            "title": {"visibility": "required", "min_length": 5, "max_length": None}
        }
    )

    form = RequestRequireTestForm(event=event)

    field = form.fields["title"]
    assert field.widget.attrs.get("data-minlength") == 5
    assert "data-maxlength" not in field.widget.attrs


@pytest.mark.django_db
def test_request_require_init_max_only_chars():
    event = EventFactory(
        cfp__fields={
            "title": {"visibility": "required", "min_length": None, "max_length": 50}
        }
    )

    form = RequestRequireTestForm(event=event)

    field = form.fields["title"]
    assert "data-minlength" not in field.widget.attrs
    assert field.widget.attrs.get("data-maxlength") == 50
