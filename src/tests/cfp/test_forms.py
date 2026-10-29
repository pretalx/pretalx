# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django import forms

from pretalx.cfp.forms import CfPFormMixin, RequestRequire, count_length
from tests.factories import EventFactory

pytestmark = pytest.mark.unit


class _CfPMixinForm(CfPFormMixin, forms.Form):
    title = forms.CharField()
    abstract = forms.CharField(required=False)
    description = forms.CharField(required=False)


class RequestRequireTestForm(RequestRequire, forms.Form):
    title = forms.CharField()
    abstract = forms.CharField(widget=forms.Textarea)
    description = forms.CharField(widget=forms.Textarea)

    def __init__(self, *args, event=None, **kwargs):
        self.event = event
        super().__init__(*args, **kwargs)

    class Meta:
        request_require = ["title", "abstract", "description"]


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
    form._update_cfp_texts("title")

    assert form.field_configuration is None
    assert list(form.fields) == ["title", "abstract", "description"]
    assert not hasattr(form.fields["title"], "original_help_text")


@pytest.mark.parametrize(
    ("config", "expected_order"),
    (
        (
            [{"key": "description"}, {"key": "abstract"}, {"key": "title"}],
            ["description", "abstract", "title"],
        ),
        ([{"key": "abstract"}], ["abstract", "title", "description"]),
        (
            [{"key": "nonexistent"}, {"key": "title"}],
            ["title", "abstract", "description"],
        ),
    ),
    ids=["reorders", "unconfigured_keep_order", "ignores_unknown_keys"],
)
def test_cfp_form_mixin_reorders_fields(config, expected_order):
    form = _CfPMixinForm(field_configuration=config)

    assert list(form.field_configuration) == [entry["key"] for entry in config]
    assert list(form.fields) == expected_order


@pytest.mark.parametrize(
    ("entry", "expected_label", "expected_help_text"),
    (
        ({}, None, ""),
        ({"label": "Custom Title"}, "Custom Title", ""),
        ({"help_text": "Some help"}, None, "Some help"),
        (
            {"label": "Talk Title", "help_text": "Max 100 chars"},
            "Talk Title",
            "Max 100 chars",
        ),
    ),
    ids=["neither", "label", "help_text", "both"],
)
def test_cfp_form_mixin_update_cfp_texts(entry, expected_label, expected_help_text):
    form = _CfPMixinForm(field_configuration=[{"key": "title", **entry}])
    form._update_cfp_texts("nonexistent")

    assert form.fields["title"].label == expected_label
    assert form.fields["title"].original_help_text == expected_help_text
    assert bool(form.fields["title"].help_text) is bool(expected_help_text)


def test_cfp_form_mixin_update_cfp_texts_preserves_added_help_text():
    class _AddedHelpMixin:
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields["title"].added_help_text = "(max 100 chars)"

    class _FormWithAddedHelp(CfPFormMixin, _AddedHelpMixin, forms.Form):
        title = forms.CharField()

    config = [{"key": "title", "help_text": "Be descriptive"}]
    form = _FormWithAddedHelp(field_configuration=config)

    help_html = str(form.fields["title"].help_text)
    assert "(max 100 chars)" in help_html


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
        ("line1\r\nline2", 11, 11, "chars"),
        ("one two three", 3, 3, "words"),
    ),
    ids=(
        "no_constraints_chars",
        "no_constraints_words",
        "chars_in_range",
        "words_in_range",
        "crlf_counts_as_one_char",
        "words_exact_count",
    ),
)
def test_request_require_validate_field_length_accepts_valid(
    value, min_length, max_length, count_in
):
    RequestRequire.validate_field_length(value, min_length, max_length, count_in)


@pytest.mark.parametrize(
    ("value", "min_length", "max_length", "count_in", "message"),
    (
        (
            "hi",
            10,
            100,
            "chars",
            "Please write between 10 and 100 characters. You wrote 2 characters.",
        ),
        (
            "a" * 200,
            10,
            100,
            "chars",
            "Please write between 10 and 100 characters. You wrote 200 characters.",
        ),
        ("one", 5, None, "words", "Please write at least 5 words. You wrote 1 words."),
        (
            "don't stop me now",
            None,
            2,
            "words",
            "Please write at most 2 words. You wrote 4 words.",
        ),
    ),
    ids=("chars_too_short", "chars_too_long", "words_too_few", "words_too_many"),
)
def test_request_require_validate_field_length_rejects_invalid(
    value, min_length, max_length, count_in, message
):
    with pytest.raises(forms.ValidationError) as excinfo:
        RequestRequire.validate_field_length(value, min_length, max_length, count_in)

    assert excinfo.value.messages == [message]


@pytest.mark.parametrize(
    ("value", "count_in", "expected"),
    (
        ("hello world", "chars", 11),
        ("  hello world  ", "chars", 11),
        ("line1\r\nline2", "chars", 11),
        ("hi \U0001f600 there", "chars", 10),
        ("\ufeffhello", "chars", 6),
        ("a\ufeffb", "chars", 3),
        ("", "chars", 0),
        (None, "chars", 0),
        ("hello world", "words", 2),
        ("  hello   world  ", "words", 2),
        ("line1\r\nline2", "words", 2),
        ("don't stop", "words", 2),
        ("state-of-the-art tooling", "words", 2),
        ("naïve café", "words", 2),
        ("3.14 is pi", "words", 3),
        ("- one\n- two", "words", 2),
        ("--- ***", "words", 0),
        ("hi \U0001f600 there", "words", 2),
        ("\ufeffhello", "words", 1),
        ("a\ufeffb", "words", 1),
        ("", "words", 0),
        (None, "words", 0),
    ),
)
def test_count_length(value, count_in, expected):
    assert count_length(value, count_in) == expected


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
    ("value", "min_number", "max_number", "message"),
    (
        (["a"], 3, 5, "Please select between 3 and 5 tags. You selected 1 tags."),
        (
            ["a", "b", "c", "d", "e", "f"],
            None,
            3,
            "Please select at most 3 tags. You selected 6 tags.",
        ),
        (None, 2, None, "Please select at least 2 tags. You selected 0 tags."),
    ),
    ids=("too_few", "too_many", "none_below_min"),
)
def test_request_require_validate_tag_count_rejects_invalid(
    value, min_number, max_number, message
):
    with pytest.raises(forms.ValidationError) as excinfo:
        RequestRequire.validate_tag_count(value, min_number, max_number)

    assert excinfo.value.messages == [message]


@pytest.mark.django_db
def test_request_require_init_applies_cfp_visibility():
    event = EventFactory(
        cfp__fields={
            "title": {"visibility": "required", "min_length": None, "max_length": None},
            "abstract": {
                "visibility": "optional",
                "min_length": None,
                "max_length": None,
            },
            "description": {
                "visibility": "do_not_ask",
                "min_length": None,
                "max_length": None,
            },
        }
    )

    form = RequestRequireTestForm(event=event)

    assert form.fields["title"].required is True
    assert form.fields["abstract"].required is False
    assert "description" not in form.fields


@pytest.mark.parametrize(
    ("min_length", "max_length", "cfp_settings", "expected_attrs", "expected_help"),
    (
        (
            5,
            100,
            {},
            {"data-minlength": 5, "data-maxlength": 100, "data-count-in": "chars"},
            " Please write between 5 and 100 characters.",
        ),
        (
            5,
            100,
            {"count_length_in": "words"},
            {"data-minlength": 5, "data-maxlength": 100, "data-count-in": "words"},
            " Please write between 5 and 100 words.",
        ),
        (
            5,
            None,
            {},
            {"data-minlength": 5, "data-count-in": "chars"},
            " Please write at least 5 characters.",
        ),
        (
            None,
            50,
            {},
            {"data-maxlength": 50, "data-count-in": "chars"},
            " Please write at most 50 characters.",
        ),
        (None, None, {}, {}, ""),
    ),
    ids=("chars", "words", "min_only", "max_only", "no_limits"),
)
@pytest.mark.django_db
def test_request_require_init_sets_length_data_attrs_and_help_text(
    min_length, max_length, cfp_settings, expected_attrs, expected_help
):
    event = EventFactory(
        cfp__fields={
            "title": {
                "visibility": "required",
                "min_length": min_length,
                "max_length": max_length,
            }
        },
        cfp__settings=cfp_settings,
    )

    form = RequestRequireTestForm(event=event)

    attrs = form.fields["title"].widget.attrs
    assert {
        key: value for key, value in attrs.items() if key.startswith("data-")
    } == expected_attrs
    assert form.fields["title"].help_text == expected_help


@pytest.mark.django_db
def test_request_require_init_field_not_in_form_is_skipped():
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


@pytest.mark.parametrize(
    ("min_number", "max_number", "expected_help"),
    ((1, 5, "Please select between 1 and 5 tags."), (None, None, "")),
    ids=["with_limits", "without_limits"],
)
@pytest.mark.django_db
def test_request_require_init_tags_help_text(min_number, max_number, expected_help):
    event = EventFactory(
        cfp__fields={
            "title": {"visibility": "required", "min_length": None, "max_length": None},
            "tags": {"visibility": "optional", "min": min_number, "max": max_number},
        }
    )

    form = RequestRequireWithTagsForm(event=event)

    assert form.fields["tags"].help_text == expected_help


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
