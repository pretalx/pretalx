import datetime as dt
from io import BytesIO
from unittest.mock import patch

import pytest
from django import forms
from django.core.files.base import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django_scopes import scopes_disabled
from i18nfield.forms import I18nFormField, I18nFormMixin, I18nTextarea, I18nTextInput

from pretalx.common.forms.mixins import (
    HierarkeyMixin,
    JsonSubfieldMixin,
    PretalxI18nFormMixin,
    PretalxI18nModelForm,
    QuestionFieldsMixin,
    ReadOnlyFlag,
    RequestRequire,
)
from pretalx.common.forms.widgets import I18nMarkdownTextarea
from pretalx.submission.models import QuestionTarget, QuestionVariant
from pretalx.submission.models.question import Answer, AnswerOption
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    EventFactory,
    QuestionFactory,
    SpeakerFactory,
    SubmissionFactory,
)

pytestmark = pytest.mark.unit


class ReadOnlyTestForm(ReadOnlyFlag, forms.Form):
    name = forms.CharField()
    email = forms.EmailField()


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


class QuestionFieldTestHelper(QuestionFieldsMixin):
    """Lightweight wrapper to test get_field() directly."""

    def __init__(self, event):
        self.event = event


class JsonSubfieldTestForm(JsonSubfieldMixin, forms.Form):
    show_schedule = forms.BooleanField(required=False)
    use_feedback = forms.BooleanField(required=False)

    class Meta:
        json_fields = {
            "show_schedule": "feature_flags",
            "use_feedback": "feature_flags",
        }


class _SaveStub(forms.Form):
    """Provides a no-op save() so HierarkeyMixin.save can call super().save()."""

    def save(self, *args, **kwargs):
        pass


class HierarkeyTestForm(HierarkeyMixin, _SaveStub):
    test_setting = forms.CharField(required=False)
    test_file = forms.FileField(required=False)

    class Meta:
        hierarkey_fields = ("test_setting", "test_file")


class I18nTestForm(PretalxI18nFormMixin, forms.Form):
    name = I18nFormField(widget=I18nTextarea, required=False)


@pytest.mark.parametrize(
    ("read_only", "expected_disabled"),
    ((True, True), (False, False)),
    ids=("read_only", "editable"),
)
def test_read_only_flag_field_disabled(read_only, expected_disabled):
    form = ReadOnlyTestForm(read_only=read_only)

    assert form.read_only is read_only
    assert form.fields["name"].disabled is expected_disabled
    assert form.fields["email"].disabled is expected_disabled


@pytest.mark.parametrize(
    ("read_only", "expected_valid"),
    ((True, False), (False, True)),
    ids=("read_only_rejects", "editable_accepts"),
)
def test_read_only_flag_clean(read_only, expected_valid):
    form = ReadOnlyTestForm(data={"name": "x", "email": "x@x.com"}, read_only=read_only)

    assert form.is_valid() is expected_valid


def test_read_only_flag_defaults_to_not_read_only():
    form = ReadOnlyTestForm()

    assert form.read_only is False


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
    """\\r\\n line breaks count as a single character."""
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
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["title"] = {
            "visibility": "required",
            "min_length": None,
            "max_length": None,
        }
        event.cfp.fields["abstract"] = {
            "visibility": "optional",
            "min_length": None,
            "max_length": None,
        }
        event.cfp.save()

    form = RequestRequireTestForm(event=event)

    assert form.fields["title"].required is True
    assert form.fields["abstract"].required is False


@pytest.mark.django_db
def test_request_require_init_removes_do_not_ask_fields():
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["title"] = {
            "visibility": "do_not_ask",
            "min_length": None,
            "max_length": None,
        }
        event.cfp.fields["abstract"] = {
            "visibility": "required",
            "min_length": None,
            "max_length": None,
        }
        event.cfp.save()

    form = RequestRequireTestForm(event=event)

    assert "title" not in form.fields
    assert "abstract" in form.fields


@pytest.mark.django_db
def test_request_require_init_adds_length_validator_with_chars():
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["title"] = {
            "visibility": "required",
            "min_length": 5,
            "max_length": 100,
        }
        event.cfp.save()

    form = RequestRequireTestForm(event=event)

    field = form.fields["title"]
    assert field.widget.attrs["data-minlength"] == 5
    assert field.widget.attrs["data-maxlength"] == 100


@pytest.mark.django_db
def test_request_require_init_word_counting_skips_data_attrs():
    """When count_length_in is 'words', data-minlength/data-maxlength are NOT set."""
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["title"] = {
            "visibility": "required",
            "min_length": 5,
            "max_length": 100,
        }
        event.cfp.settings["count_length_in"] = "words"
        event.cfp.save()

    form = RequestRequireTestForm(event=event)

    field = form.fields["title"]
    assert "data-minlength" not in field.widget.attrs
    assert "data-maxlength" not in field.widget.attrs


@pytest.mark.django_db
def test_request_require_init_adds_help_text_for_length():
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["title"] = {
            "visibility": "required",
            "min_length": 10,
            "max_length": 200,
        }
        event.cfp.save()

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

    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["title"] = {
            "visibility": "required",
            "min_length": None,
            "max_length": None,
        }
        event.cfp.fields["description"] = {
            "visibility": "optional",
            "min_length": None,
            "max_length": None,
        }
        event.cfp.save()

    form = FormWithoutDescription(event=event)

    assert "title" in form.fields
    assert "description" not in form.fields


@pytest.mark.django_db
def test_request_require_init_tags_with_limits():
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["title"] = {
            "visibility": "required",
            "min_length": None,
            "max_length": None,
        }
        event.cfp.fields["tags"] = {"visibility": "optional", "min": 1, "max": 5}
        event.cfp.save()

    form = RequestRequireWithTagsForm(event=event)

    field = form.fields["tags"]
    assert field.help_text == "Please select between 1 and 5 tags."


@pytest.mark.django_db
def test_request_require_init_tags_without_limits_preserves_help_text():
    """When tags have no limits but have original help_text, it is preserved."""
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["title"] = {
            "visibility": "required",
            "min_length": None,
            "max_length": None,
        }
        event.cfp.fields["tags"] = {"visibility": "optional", "min": None, "max": None}
        event.cfp.save()

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
    """When tags have no limits and no original help_text, help_text stays empty."""
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["title"] = {
            "visibility": "required",
            "min_length": None,
            "max_length": None,
        }
        event.cfp.fields["tags"] = {"visibility": "optional", "min": None, "max": None}
        event.cfp.save()

    form = RequestRequireWithTagsForm(event=event)

    assert not form.fields["tags"].help_text


@pytest.mark.django_db
def test_request_require_init_min_only_chars():
    """When only min_length is set with char counting, data-minlength is set."""
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["title"] = {
            "visibility": "required",
            "min_length": 5,
            "max_length": None,
        }
        event.cfp.save()

    form = RequestRequireTestForm(event=event)

    field = form.fields["title"]
    assert field.widget.attrs.get("data-minlength") == 5
    assert "data-maxlength" not in field.widget.attrs


@pytest.mark.django_db
def test_request_require_init_max_only_chars():
    """When only max_length is set with char counting, data-maxlength is set."""
    with scopes_disabled():
        event = EventFactory()
        event.cfp.fields["title"] = {
            "visibility": "required",
            "min_length": None,
            "max_length": 50,
        }
        event.cfp.save()

    form = RequestRequireTestForm(event=event)

    field = form.fields["title"]
    assert "data-minlength" not in field.widget.attrs
    assert field.widget.attrs.get("data-maxlength") == 50


@pytest.mark.django_db
def test_question_field_get_field_boolean():
    with scopes_disabled():
        question = QuestionFactory(
            variant=QuestionVariant.BOOLEAN, question_required="required"
        )

    helper = QuestionFieldTestHelper(question.event)
    field = helper.get_field(
        question=question, initial=None, initial_object=None, readonly=False
    )

    assert isinstance(field, forms.BooleanField)
    assert field.required is True


@pytest.mark.django_db
def test_question_field_get_field_boolean_with_initial_true():
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.BOOLEAN)

    helper = QuestionFieldTestHelper(question.event)
    field = helper.get_field(
        question=question, initial="True", initial_object=None, readonly=False
    )

    assert field.initial is True


@pytest.mark.django_db
def test_question_field_get_field_number():
    with scopes_disabled():
        question = QuestionFactory(
            variant=QuestionVariant.NUMBER, min_number=1, max_number=100
        )

    helper = QuestionFieldTestHelper(question.event)
    field = helper.get_field(
        question=question, initial="42", initial_object=None, readonly=False
    )

    assert isinstance(field, forms.DecimalField)
    assert field.min_value == 1
    assert field.max_value == 100
    assert field.initial == "42"


@pytest.mark.django_db
def test_question_field_get_field_string_with_char_counting():
    with scopes_disabled():
        question = QuestionFactory(
            variant=QuestionVariant.STRING, min_length=10, max_length=200
        )

    helper = QuestionFieldTestHelper(question.event)
    field = helper.get_field(
        question=question, initial=None, initial_object=None, readonly=False
    )

    assert isinstance(field, forms.CharField)
    assert field.widget.attrs.get("data-minlength") == 10
    assert field.widget.attrs.get("data-maxlength") == 200


@pytest.mark.django_db
def test_question_field_get_field_string_with_word_counting():
    """When count_length_in is 'words', data attrs are NOT set."""
    with scopes_disabled():
        question = QuestionFactory(
            variant=QuestionVariant.STRING, min_length=5, max_length=50
        )
        question.event.cfp.settings["count_length_in"] = "words"
        question.event.cfp.save()

    helper = QuestionFieldTestHelper(question.event)
    field = helper.get_field(
        question=question, initial=None, initial_object=None, readonly=False
    )

    assert isinstance(field, forms.CharField)
    assert "data-minlength" not in field.widget.attrs
    assert "data-maxlength" not in field.widget.attrs


@pytest.mark.django_db
def test_question_field_get_field_string_without_length_constraints():
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.STRING)

    helper = QuestionFieldTestHelper(question.event)
    field = helper.get_field(
        question=question, initial=None, initial_object=None, readonly=False
    )

    assert isinstance(field, forms.CharField)
    assert "data-minlength" not in field.widget.attrs
    assert "data-maxlength" not in field.widget.attrs


@pytest.mark.django_db
def test_question_field_get_field_url():
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.URL)

    helper = QuestionFieldTestHelper(question.event)
    field = helper.get_field(
        question=question,
        initial="https://example.com",
        initial_object=None,
        readonly=False,
    )

    assert isinstance(field, forms.URLField)
    assert field.initial == "https://example.com"


@pytest.mark.django_db
def test_question_field_get_field_text_with_char_counting():
    with scopes_disabled():
        question = QuestionFactory(
            variant=QuestionVariant.TEXT, min_length=20, max_length=500
        )

    helper = QuestionFieldTestHelper(question.event)
    field = helper.get_field(
        question=question, initial=None, initial_object=None, readonly=False
    )

    assert isinstance(field, forms.CharField)
    assert isinstance(field.widget, forms.Textarea)
    assert field.widget.attrs.get("data-minlength") == 20
    assert field.widget.attrs.get("data-maxlength") == 500


@pytest.mark.django_db
def test_question_field_get_field_text_with_word_counting():
    """When counting words, data attrs are skipped for TEXT questions too."""
    with scopes_disabled():
        question = QuestionFactory(
            variant=QuestionVariant.TEXT, min_length=5, max_length=100
        )
        question.event.cfp.settings["count_length_in"] = "words"
        question.event.cfp.save()

    helper = QuestionFieldTestHelper(question.event)
    field = helper.get_field(
        question=question, initial=None, initial_object=None, readonly=False
    )

    assert isinstance(field, forms.CharField)
    assert "data-minlength" not in field.widget.attrs
    assert "data-maxlength" not in field.widget.attrs


@pytest.mark.django_db
def test_question_field_get_field_text_without_length_constraints():
    """TEXT question with char counting but no min/max still skips data attrs."""
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.TEXT)

    helper = QuestionFieldTestHelper(question.event)
    field = helper.get_field(
        question=question, initial=None, initial_object=None, readonly=False
    )

    assert isinstance(field, forms.CharField)
    assert isinstance(field.widget, forms.Textarea)
    assert "data-minlength" not in field.widget.attrs
    assert "data-maxlength" not in field.widget.attrs


@pytest.mark.django_db
def test_question_field_get_field_file():
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.FILE)

    helper = QuestionFieldTestHelper(question.event)
    field = helper.get_field(
        question=question, initial=None, initial_object=None, readonly=False
    )

    assert isinstance(field, forms.FileField)


@pytest.mark.django_db
def test_question_field_get_field_choices():
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.CHOICES)
        opt1 = AnswerOptionFactory(question=question, answer="Option A")
        opt2 = AnswerOptionFactory(question=question, answer="Option B")

    helper = QuestionFieldTestHelper(question.event)
    with scopes_disabled():
        field = helper.get_field(
            question=question, initial=None, initial_object=None, readonly=False
        )

    assert isinstance(field, forms.ModelChoiceField)
    assert set(field.queryset) == {opt1, opt2}


@pytest.mark.django_db
def test_question_field_get_field_multiple():
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.MULTIPLE)
        opt1 = AnswerOptionFactory(question=question, answer="Option A")
        opt2 = AnswerOptionFactory(question=question, answer="Option B")

    helper = QuestionFieldTestHelper(question.event)
    with scopes_disabled():
        field = helper.get_field(
            question=question, initial=None, initial_object=None, readonly=False
        )

    assert isinstance(field, forms.ModelMultipleChoiceField)
    assert set(field.queryset) == {opt1, opt2}


@pytest.mark.django_db
def test_question_field_get_field_date_with_constraints():
    with scopes_disabled():
        question = QuestionFactory(
            variant=QuestionVariant.DATE,
            min_date=dt.date(2025, 1, 1),
            max_date=dt.date(2025, 12, 31),
        )

    helper = QuestionFieldTestHelper(question.event)
    field = helper.get_field(
        question=question, initial=None, initial_object=None, readonly=False
    )

    assert isinstance(field, forms.DateField)
    assert field.widget.attrs.get("data-date-start-date") == "2025-01-01"
    assert field.widget.attrs.get("data-date-end-date") == "2025-12-31"
    assert len(field.validators) == 2


@pytest.mark.django_db
def test_question_field_get_field_date_with_initial():
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.DATE)

    helper = QuestionFieldTestHelper(question.event)
    field = helper.get_field(
        question=question, initial="2025-06-15", initial_object=None, readonly=False
    )

    assert field.initial == dt.date(2025, 6, 15)


@pytest.mark.django_db
def test_question_field_get_field_datetime_with_constraints():
    min_dt = dt.datetime(2025, 1, 1, 0, 0, tzinfo=dt.UTC)
    max_dt = dt.datetime(2025, 12, 31, 23, 59, tzinfo=dt.UTC)
    with scopes_disabled():
        question = QuestionFactory(
            variant=QuestionVariant.DATETIME, min_datetime=min_dt, max_datetime=max_dt
        )

    helper = QuestionFieldTestHelper(question.event)
    field = helper.get_field(
        question=question, initial=None, initial_object=None, readonly=False
    )

    assert isinstance(field, forms.DateTimeField)
    assert field.widget.attrs.get("min") == min_dt.isoformat()
    assert field.widget.attrs.get("max") == max_dt.isoformat()
    assert len(field.validators) == 2


@pytest.mark.django_db
def test_question_field_get_field_datetime_with_initial():
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.DATETIME)

    helper = QuestionFieldTestHelper(question.event)
    field = helper.get_field(
        question=question,
        initial="2025-06-15T10:30:00+00:00",
        initial_object=None,
        readonly=False,
    )

    expected = dt.datetime(2025, 6, 15, 10, 30, tzinfo=dt.UTC).astimezone(
        question.event.tz
    )
    assert field.initial == expected


@pytest.mark.django_db
def test_question_field_get_field_read_only():
    with scopes_disabled():
        question = QuestionFactory(
            variant=QuestionVariant.STRING,
            freeze_after=dt.datetime(2020, 1, 1, tzinfo=dt.UTC),
        )

    helper = QuestionFieldTestHelper(question.event)
    field = helper.get_field(
        question=question, initial=None, initial_object=None, readonly=False
    )

    assert field.disabled is True


@pytest.mark.django_db
def test_question_field_get_field_readonly_param():
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.STRING)

    helper = QuestionFieldTestHelper(question.event)
    field = helper.get_field(
        question=question, initial=None, initial_object=None, readonly=True
    )

    assert field.disabled is True


@pytest.mark.django_db
def test_question_field_get_field_date_no_constraints():
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.DATE)

    helper = QuestionFieldTestHelper(question.event)
    field = helper.get_field(
        question=question, initial=None, initial_object=None, readonly=False
    )

    assert isinstance(field, forms.DateField)
    assert "data-date-start-date" not in field.widget.attrs
    assert "data-date-end-date" not in field.widget.attrs


@pytest.mark.django_db
def test_question_field_get_field_datetime_no_constraints():
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.DATETIME)

    helper = QuestionFieldTestHelper(question.event)
    field = helper.get_field(
        question=question, initial=None, initial_object=None, readonly=False
    )

    assert isinstance(field, forms.DateTimeField)
    assert "min" not in field.widget.attrs
    assert "max" not in field.widget.attrs


@pytest.mark.django_db
def test_question_field_get_field_choices_with_initial_object():
    """When there's an existing answer for a choice question, its option is the initial."""
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.CHOICES)
        opt = AnswerOptionFactory(question=question, answer="Selected")
        AnswerOptionFactory(question=question, answer="Other")
        answer = AnswerFactory(
            question=question, submission=SubmissionFactory(event=question.event)
        )
        answer.options.add(opt)

    helper = QuestionFieldTestHelper(question.event)
    with scopes_disabled():
        field = helper.get_field(
            question=question, initial=None, initial_object=answer, readonly=False
        )

    assert field.initial == opt


@pytest.mark.django_db
def test_question_field_get_field_multiple_with_initial_object():
    """When there's an existing answer for a multiple-choice question, its options are initial."""
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.MULTIPLE)
        opt1 = AnswerOptionFactory(question=question, answer="A")
        opt2 = AnswerOptionFactory(question=question, answer="B")
        answer = AnswerFactory(
            question=question, submission=SubmissionFactory(event=question.event)
        )
        answer.options.add(opt1, opt2)

    helper = QuestionFieldTestHelper(question.event)
    with scopes_disabled():
        field = helper.get_field(
            question=question, initial=None, initial_object=answer, readonly=False
        )

    assert set(field.initial) == {opt1, opt2}


@pytest.mark.django_db
def test_question_save_questions_creates_answer_for_submission():
    with scopes_disabled():
        submission = SubmissionFactory()
        question = QuestionFactory(
            event=submission.event,
            variant=QuestionVariant.STRING,
            target=QuestionTarget.SUBMISSION,
        )

    helper = QuestionFieldTestHelper(question.event)
    helper.submission = submission
    helper.speaker = None
    helper.review = None

    field = forms.CharField()
    field.question = question
    field.answer = None
    helper.fields = {f"question_{question.pk}": field}

    with scopes_disabled():
        helper.save_questions(f"question_{question.pk}", "My answer")
        answer = Answer.objects.get(question=question, submission=submission)

    assert answer.answer == "My answer"
    assert field.answer == answer


@pytest.mark.django_db
def test_question_save_questions_updates_existing_answer():
    with scopes_disabled():
        submission = SubmissionFactory()
        question = QuestionFactory(
            event=submission.event,
            variant=QuestionVariant.STRING,
            target=QuestionTarget.SUBMISSION,
        )
        answer = AnswerFactory(question=question, submission=submission, answer="Old")

    helper = QuestionFieldTestHelper(question.event)
    helper.submission = submission
    helper.speaker = None
    helper.review = None

    field = forms.CharField()
    field.question = question
    field.answer = answer
    helper.fields = {f"question_{question.pk}": field}

    with scopes_disabled():
        helper.save_questions(f"question_{question.pk}", "New answer")

    answer.refresh_from_db()
    assert answer.answer == "New answer"


@pytest.mark.django_db
def test_question_save_questions_deletes_answer_on_empty_value():
    with scopes_disabled():
        submission = SubmissionFactory()
        question = QuestionFactory(
            event=submission.event,
            variant=QuestionVariant.STRING,
            target=QuestionTarget.SUBMISSION,
        )
        answer = AnswerFactory(question=question, submission=submission, answer="Old")

    helper = QuestionFieldTestHelper(question.event)
    helper.submission = submission
    helper.speaker = None
    helper.review = None

    field = forms.CharField()
    field.question = question
    field.answer = answer
    helper.fields = {f"question_{question.pk}": field}

    with scopes_disabled():
        helper.save_questions(f"question_{question.pk}", "")
        assert not Answer.objects.filter(pk=answer.pk).exists()
    assert field.answer is None


@pytest.mark.django_db
def test_question_save_questions_noop_for_empty_value_without_existing_answer():
    """When value is empty/None and there's no existing answer, nothing happens."""
    with scopes_disabled():
        submission = SubmissionFactory()
        question = QuestionFactory(
            event=submission.event,
            variant=QuestionVariant.STRING,
            target=QuestionTarget.SUBMISSION,
        )

    helper = QuestionFieldTestHelper(question.event)
    helper.submission = submission
    helper.speaker = None
    helper.review = None

    field = forms.CharField()
    field.question = question
    field.answer = None
    helper.fields = {f"question_{question.pk}": field}

    with scopes_disabled():
        helper.save_questions(f"question_{question.pk}", "")
        assert not Answer.objects.filter(question=question).exists()


@pytest.mark.django_db
def test_question_save_to_answer_model_choice_field_new():
    """_save_to_answer with ModelChoiceField creates answer with option."""
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.CHOICES)
        opt = AnswerOptionFactory(question=question, answer="Selected")
        submission = SubmissionFactory(event=question.event)

    helper = QuestionFieldTestHelper(question.event)
    with scopes_disabled():
        choices = AnswerOption.objects.filter(question=question)
        field = forms.ModelChoiceField(queryset=choices)
        answer = Answer(question=question, submission=submission)

        helper._save_to_answer(field, answer, opt)

        assert answer.pk is not None
        assert answer.answer == opt.answer
        assert list(answer.options.all()) == [opt]


@pytest.mark.django_db
def test_question_save_to_answer_model_choice_field_update_clears_old():
    """When updating a ModelChoiceField answer, old options are cleared first."""
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.CHOICES)
        opt1 = AnswerOptionFactory(question=question, answer="Old")
        opt2 = AnswerOptionFactory(question=question, answer="New")
        submission = SubmissionFactory(event=question.event)
        answer = AnswerFactory(question=question, submission=submission)
        answer.options.add(opt1)

    helper = QuestionFieldTestHelper(question.event)
    with scopes_disabled():
        choices = AnswerOption.objects.filter(question=question)
        field = forms.ModelChoiceField(queryset=choices)

        helper._save_to_answer(field, answer, opt2)

        answer.refresh_from_db()
        assert list(answer.options.all()) == [opt2]
        assert answer.answer == opt2.answer


@pytest.mark.django_db
def test_question_save_to_answer_model_choice_field_empty_value():
    """When ModelChoiceField value is empty, answer is saved with empty string."""
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.CHOICES)
        AnswerOptionFactory(question=question)
        submission = SubmissionFactory(event=question.event)
        answer = AnswerFactory(question=question, submission=submission)

    helper = QuestionFieldTestHelper(question.event)
    with scopes_disabled():
        choices = AnswerOption.objects.filter(question=question)
        field = forms.ModelChoiceField(queryset=choices, required=False)

        helper._save_to_answer(field, answer, None)

        answer.refresh_from_db()
        assert answer.answer == ""
        assert list(answer.options.all()) == []


@pytest.mark.django_db
def test_question_save_to_answer_model_multiple_choice_field_new():
    """_save_to_answer with ModelMultipleChoiceField creates answer with options."""
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.MULTIPLE)
        opt1 = AnswerOptionFactory(question=question, answer="A")
        opt2 = AnswerOptionFactory(question=question, answer="B")
        submission = SubmissionFactory(event=question.event)

    helper = QuestionFieldTestHelper(question.event)
    with scopes_disabled():
        choices = AnswerOption.objects.filter(question=question)
        field = forms.ModelMultipleChoiceField(queryset=choices)
        answer = Answer(question=question, submission=submission)

        helper._save_to_answer(
            field, answer, AnswerOption.objects.filter(pk__in=[opt1.pk, opt2.pk])
        )

        assert answer.pk is not None
        assert set(answer.options.all()) == {opt1, opt2}
        assert answer.answer == "A, B"


@pytest.mark.django_db
def test_question_save_to_answer_model_multiple_choice_field_update_clears():
    """When updating, old options are cleared before adding new ones."""
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.MULTIPLE)
        opt1 = AnswerOptionFactory(question=question, answer="Old")
        opt2 = AnswerOptionFactory(question=question, answer="New")
        submission = SubmissionFactory(event=question.event)
        answer = AnswerFactory(question=question, submission=submission)
        answer.options.add(opt1)

    helper = QuestionFieldTestHelper(question.event)
    with scopes_disabled():
        choices = AnswerOption.objects.filter(question=question)
        field = forms.ModelMultipleChoiceField(queryset=choices)

        helper._save_to_answer(field, answer, AnswerOption.objects.filter(pk=opt2.pk))

        answer.refresh_from_db()
        assert list(answer.options.all()) == [opt2]


@pytest.mark.django_db
def test_question_save_to_answer_model_multiple_choice_empty_value():
    """When value is an empty queryset, answer is saved with no options."""
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.MULTIPLE)
        AnswerOptionFactory(question=question, answer="Opt")
        submission = SubmissionFactory(event=question.event)

    helper = QuestionFieldTestHelper(question.event)
    with scopes_disabled():
        choices = AnswerOption.objects.filter(question=question)
        field = forms.ModelMultipleChoiceField(queryset=choices, required=False)
        answer = Answer(question=question, submission=submission)

        helper._save_to_answer(field, answer, AnswerOption.objects.none())

        assert answer.pk is not None
        assert list(answer.options.all()) == []


@pytest.mark.django_db
def test_question_save_to_answer_file_field():
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.FILE)
        submission = SubmissionFactory(event=question.event)

    helper = QuestionFieldTestHelper(question.event)
    field = forms.FileField()
    answer = Answer(question=question, submission=submission)
    upload = SimpleUploadedFile("test.pdf", b"content", content_type="application/pdf")

    with scopes_disabled():
        helper._save_to_answer(field, answer, upload)

    assert answer.pk is not None
    assert answer.answer.startswith("file://")


@pytest.mark.django_db
def test_question_save_to_answer_file_field_existing_answer():
    """When a FileField value is not an UploadedFile, answer.answer is preserved."""
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.FILE)
        submission = SubmissionFactory(event=question.event)
        answer = AnswerFactory(
            question=question, submission=submission, answer="file://existing.pdf"
        )

    helper = QuestionFieldTestHelper(question.event)
    field = forms.FileField()
    # Pass a non-UploadedFile value (e.g. existing file path string)
    with scopes_disabled():
        helper._save_to_answer(field, answer, "file://existing.pdf")

    answer.refresh_from_db()
    assert answer.answer == "file://existing.pdf"


@pytest.mark.django_db
def test_question_save_to_answer_plain_text():
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.STRING)
        submission = SubmissionFactory(event=question.event)

    helper = QuestionFieldTestHelper(question.event)
    field = forms.CharField()
    answer = Answer(question=question, submission=submission)

    with scopes_disabled():
        helper._save_to_answer(field, answer, "test answer")

    assert answer.pk is not None
    assert answer.answer == "test answer"


@pytest.mark.django_db
def test_question_save_questions_creates_speaker_answer():
    with scopes_disabled():
        speaker = SpeakerFactory()
        question = QuestionFactory(
            event=speaker.event,
            variant=QuestionVariant.STRING,
            target=QuestionTarget.SPEAKER,
        )

    helper = QuestionFieldTestHelper(question.event)
    helper.submission = None
    helper.speaker = speaker
    helper.review = None

    field = forms.CharField()
    field.question = question
    field.answer = None
    helper.fields = {f"question_{question.pk}": field}

    with scopes_disabled():
        helper.save_questions(f"question_{question.pk}", "Speaker answer")
        answer = Answer.objects.get(question=question, speaker=speaker)

    assert answer.answer == "Speaker answer"


@pytest.mark.django_db
def test_json_subfield_mixin_init_reads_existing_values():
    event = EventFactory()
    event.feature_flags["show_schedule"] = True
    event.feature_flags["use_feedback"] = False
    event.save()

    form = JsonSubfieldTestForm(obj=event)

    assert form.fields["show_schedule"].initial is True
    assert form.fields["use_feedback"].initial is False


@pytest.mark.django_db
def test_json_subfield_mixin_init_uses_defaults_for_missing_fields():
    """When a JSON field isn't in the data dict yet, the model field default is used."""
    event = EventFactory()
    # Remove the key to simulate a newly-added form field
    event.feature_flags.pop("show_schedule", None)
    event.save()

    form = JsonSubfieldTestForm(obj=event)

    # Should use the default from Event._meta.get_field("feature_flags").default()
    defaults = event._meta.get_field("feature_flags").default()
    assert form.fields["show_schedule"].initial == defaults.get("show_schedule")


@pytest.mark.django_db
def test_json_subfield_mixin_save_writes_values():
    event = EventFactory()
    form = JsonSubfieldTestForm(
        data={"show_schedule": True, "use_feedback": True}, obj=event
    )
    assert form.is_valid()

    form.instance = event
    form.save()

    event.refresh_from_db()
    assert event.feature_flags["show_schedule"] is True
    assert event.feature_flags["use_feedback"] is True


@pytest.mark.django_db
def test_json_subfield_mixin_save_commit_false():
    """When commit=False, instance is not saved to the database."""
    event = EventFactory()
    original_flags = dict(event.feature_flags)
    form = JsonSubfieldTestForm(
        data={"show_schedule": True, "use_feedback": True}, obj=event
    )
    assert form.is_valid()

    form.instance = event
    result = form.save(commit=False)

    # Instance attributes updated in memory
    assert result.feature_flags["show_schedule"] is True
    # But database still has original values
    event.refresh_from_db()
    assert event.feature_flags.get("show_schedule") == original_flags.get(
        "show_schedule"
    )


@pytest.mark.django_db
def test_json_subfield_mixin_init_with_obj_kwarg():
    """The 'obj' kwarg sets self.instance when no instance exists."""
    event = EventFactory()
    form = JsonSubfieldTestForm(obj=event)

    assert form.instance is event


@pytest.mark.django_db
def test_json_subfield_mixin_init_with_existing_instance():
    """When self.instance is already set (e.g. ModelForm), it's not overridden."""
    event = EventFactory()

    class PreSetInstanceForm(JsonSubfieldMixin, forms.Form):
        show_schedule = forms.BooleanField(required=False)

        class Meta:
            json_fields = {"show_schedule": "feature_flags"}

        def __init__(self, *args, **kwargs):
            self.instance = kwargs.pop("instance")
            super().__init__(*args, **kwargs)

    form = PreSetInstanceForm(instance=event)

    assert form.instance is event


@pytest.mark.django_db
def test_json_subfield_mixin_init_with_self_obj_fallback():
    """When no 'obj' kwarg but self.obj exists, instance is set from self.obj."""
    event = EventFactory()

    class ObjForm(JsonSubfieldMixin, forms.Form):
        show_schedule = forms.BooleanField(required=False)

        class Meta:
            json_fields = {"show_schedule": "feature_flags"}

        def __init__(self, *args, **kwargs):
            self.obj = kwargs.pop("obj_attr")
            super().__init__(*args, **kwargs)

    form = ObjForm(obj_attr=event)

    assert form.instance is event


@pytest.mark.django_db
def test_json_subfield_mixin_init_without_obj_or_instance_raises():
    """When neither obj kwarg, self.obj, nor instance is provided, accessing
    self.instance in the field initialization raises AttributeError."""
    EventFactory()

    class BareForm(JsonSubfieldMixin, forms.Form):
        show_schedule = forms.BooleanField(required=False)

        class Meta:
            json_fields = {"show_schedule": "feature_flags"}

    with pytest.raises(AttributeError):
        BareForm()


@pytest.mark.django_db
def test_json_subfield_mixin_save_delegates_to_super():
    """When super has a save() method (e.g. ModelForm), it is called."""

    class BaseSave(forms.Form):
        """Simulates a ModelForm-like base with a save() method."""

        save_called = False

        def save(self, *args, **kwargs):
            self.save_called = True
            return self.instance

    class FormWithSave(JsonSubfieldMixin, BaseSave):
        test_field = forms.BooleanField(required=False)

        class Meta:
            json_fields = {"test_field": "feature_flags"}

    event = EventFactory()
    form = FormWithSave(data={"test_field": True}, obj=event)
    assert form.is_valid()

    result = form.save()

    assert form.save_called is True
    assert result.feature_flags["test_field"] is True


@pytest.mark.django_db
def test_hierarkey_mixin_init_loads_settings():
    event = EventFactory()
    event.settings.set("test_setting", "hello")

    form = HierarkeyTestForm(obj=event, attribute_name="settings", initial={})

    assert form.initial.get("test_setting") == "hello"


@pytest.mark.django_db
def test_hierarkey_mixin_save_changed_value():
    event = EventFactory()
    event.settings.set("test_setting", "old_value")

    form = HierarkeyTestForm(
        data={"test_setting": "new_value"},
        obj=event,
        attribute_name="settings",
        initial={},
    )
    assert form.is_valid()

    HierarkeyMixin.save(form)

    assert event.settings.get("test_setting") == "new_value"


@pytest.mark.django_db
def test_hierarkey_mixin_save_unchanged_value():
    """When value matches what's already stored, no update happens."""
    event = EventFactory()
    event.settings.set("test_setting", "same")

    form = HierarkeyTestForm(
        data={"test_setting": "same"}, obj=event, attribute_name="settings", initial={}
    )
    assert form.is_valid()

    HierarkeyMixin.save(form)

    assert event.settings.get("test_setting") == "same"


@pytest.mark.django_db
def test_hierarkey_mixin_save_none_value_deletes():
    """When value is None, the setting is deleted."""
    event = EventFactory()
    event.settings.set("test_setting", "will_be_deleted")

    form = HierarkeyTestForm(data={}, obj=event, attribute_name="settings", initial={})
    form.cleaned_data = {"test_setting": None, "test_file": None}

    HierarkeyMixin.save(form)

    assert event.settings.get("test_setting") is None


@pytest.mark.django_db
def test_hierarkey_mixin_save_uploaded_file():
    """When value is an UploadedFile, the file is stored and setting updated."""
    event = EventFactory()
    upload = SimpleUploadedFile("logo.png", b"png data", content_type="image/png")

    form = HierarkeyTestForm(
        data={},
        files={"test_file": upload},
        obj=event,
        attribute_name="settings",
        initial={},
    )
    form.cleaned_data = {"test_setting": None, "test_file": upload}

    HierarkeyMixin.save(form)

    stored = event.settings.get("test_file", as_type=File)
    assert f"event-settings/{event.pk}/" in stored.name
    assert "logo.png" in stored.name


@pytest.mark.django_db
def test_hierarkey_mixin_save_uploaded_file_deletes_old():
    """When uploading a new file, the old one is deleted from storage."""
    event = EventFactory()

    # First, upload a file through the full save path so it exists in storage
    old_upload = SimpleUploadedFile("old.png", b"old data", content_type="image/png")
    form1 = HierarkeyTestForm(
        data={},
        files={"test_file": old_upload},
        obj=event,
        attribute_name="settings",
        initial={},
    )
    form1.cleaned_data = {"test_setting": None, "test_file": old_upload}
    HierarkeyMixin.save(form1)

    # Now upload a replacement file
    new_upload = SimpleUploadedFile("new.png", b"new data", content_type="image/png")
    form2 = HierarkeyTestForm(
        data={},
        files={"test_file": new_upload},
        obj=event,
        attribute_name="settings",
        initial={},
    )
    form2.cleaned_data = {"test_setting": None, "test_file": new_upload}
    HierarkeyMixin.save(form2)

    stored = event.settings.get("test_file", as_type=File)
    assert f"event-settings/{event.pk}/" in stored.name
    assert "new.png" in stored.name


@pytest.mark.django_db
def test_hierarkey_mixin_save_file_unchanged():
    """When value is a plain File (not UploadedFile), it's skipped."""
    event = EventFactory()
    event.settings.set("test_setting", "keep_this")
    plain_file = File(BytesIO(b"content"), name="existing.txt")

    form = HierarkeyTestForm(
        data={"test_setting": "keep_this"},
        obj=event,
        attribute_name="settings",
        initial={},
    )
    form.cleaned_data = {"test_setting": "keep_this", "test_file": plain_file}

    HierarkeyMixin.save(form)

    assert event.settings.get("test_setting") == "keep_this"


@pytest.mark.django_db
def test_hierarkey_mixin_save_empty_file_field_deletes():
    """When a FileField value becomes empty, the stored file is deleted."""
    event = EventFactory()

    # First upload a file through the save path so it exists in storage
    upload = SimpleUploadedFile("logo.png", b"data", content_type="image/png")
    form1 = HierarkeyTestForm(
        data={},
        files={"test_file": upload},
        obj=event,
        attribute_name="settings",
        initial={},
    )
    form1.cleaned_data = {"test_setting": None, "test_file": upload}
    HierarkeyMixin.save(form1)
    assert "logo.png" in event.settings.get("test_file", as_type=File).name

    # Now submit with empty file value to trigger deletion
    form2 = HierarkeyTestForm(
        data={"test_setting": ""}, obj=event, attribute_name="settings", initial={}
    )
    form2.cleaned_data = {"test_setting": "", "test_file": None}

    HierarkeyMixin.save(form2)

    assert event.settings.get("test_file") is None


@pytest.mark.django_db
def test_hierarkey_mixin_save_uploaded_file_delete_old_oserror():
    """When deleting the old file fails with OSError, the new upload still proceeds."""
    event = EventFactory()

    # Upload initial file
    old_upload = SimpleUploadedFile("old.png", b"old", content_type="image/png")
    form1 = HierarkeyTestForm(
        data={},
        files={"test_file": old_upload},
        obj=event,
        attribute_name="settings",
        initial={},
    )
    form1.cleaned_data = {"test_setting": None, "test_file": old_upload}
    HierarkeyMixin.save(form1)

    # Replace with new file, but mock delete to raise OSError
    new_upload = SimpleUploadedFile("new.png", b"new", content_type="image/png")
    form2 = HierarkeyTestForm(
        data={},
        files={"test_file": new_upload},
        obj=event,
        attribute_name="settings",
        initial={},
    )
    form2.cleaned_data = {"test_setting": None, "test_file": new_upload}

    with patch("pretalx.common.forms.mixins.default_storage") as mock_storage:
        mock_storage.delete.side_effect = OSError("disk error")
        mock_storage.save.return_value = "event-settings/new.png"
        HierarkeyMixin.save(form2)

    assert event.settings.get("test_file") is not None


@pytest.mark.django_db
def test_hierarkey_mixin_save_clear_file_delete_oserror():
    """When deleting a cleared file fails with OSError, the setting is still removed."""
    event = EventFactory()

    # Upload initial file
    upload = SimpleUploadedFile("logo.png", b"data", content_type="image/png")
    form1 = HierarkeyTestForm(
        data={},
        files={"test_file": upload},
        obj=event,
        attribute_name="settings",
        initial={},
    )
    form1.cleaned_data = {"test_setting": None, "test_file": upload}
    HierarkeyMixin.save(form1)

    # Clear the file, but mock delete to raise OSError
    form2 = HierarkeyTestForm(
        data={"test_setting": ""}, obj=event, attribute_name="settings", initial={}
    )
    form2.cleaned_data = {"test_setting": "", "test_file": None}

    with patch("pretalx.common.forms.mixins.default_storage") as mock_storage:
        mock_storage.delete.side_effect = OSError("disk error")
        HierarkeyMixin.save(form2)

    assert event.settings.get("test_file") is None


@pytest.mark.django_db
def test_hierarkey_mixin_get_new_filename():
    event = EventFactory()
    form = HierarkeyTestForm(obj=event, attribute_name="settings", initial={})

    filename = form.get_new_filename("logo.png")

    assert f"event-settings/{event.pk}/" in filename
    assert filename.endswith(".png")
    assert "logo.png." in filename


def test_pretalx_i18n_form_mixin_replaces_textarea_with_markdown():
    """I18nTextarea widgets are replaced with I18nMarkdownTextarea."""
    form = I18nTestForm(locales=["en"])

    assert isinstance(form.fields["name"].widget, I18nMarkdownTextarea)


def test_pretalx_i18n_form_mixin_sets_placeholder():
    """When an I18nFormField has no placeholder, it's set to the field label."""
    form = I18nTestForm(locales=["en"])

    assert (
        form.fields["name"].widget.attrs.get("placeholder") == form.fields["name"].label
    )


def test_pretalx_i18n_form_mixin_preserves_existing_placeholder():
    """When an I18nFormField already has a placeholder, it's preserved."""

    class _InjectPlaceholder(I18nFormMixin):
        """Sets placeholder after I18nFormMixin sets up widgets but before
        PretalxI18nFormMixin checks for placeholders."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            for field in self.fields.values():
                if isinstance(field, I18nFormField):
                    field.widget.attrs["placeholder"] = "Pre-existing"

    class I18nWithPlaceholder(PretalxI18nFormMixin, _InjectPlaceholder, forms.Form):
        name = I18nFormField(widget=I18nTextarea, required=False)
        extra = forms.CharField(required=False)

    form = I18nWithPlaceholder(locales=["en"])

    assert form.fields["name"].widget.attrs["placeholder"] == "Pre-existing"


def test_pretalx_i18n_form_mixin_skips_non_i18n_fields():
    """Non-I18nFormField fields are left untouched by the mixin."""

    class MixedForm(PretalxI18nFormMixin, forms.Form):
        plain = forms.CharField(required=False)
        i18n_name = I18nFormField(widget=I18nTextarea, required=False)

    form = MixedForm(locales=["en"])

    assert isinstance(form.fields["plain"], forms.CharField)
    assert "placeholder" not in form.fields["plain"].widget.attrs


def test_pretalx_i18n_form_mixin_non_textarea_i18n_widget():
    """I18nFormField with a non-I18nTextarea widget keeps its widget type."""

    class I18nTextInputForm(PretalxI18nFormMixin, forms.Form):
        name = I18nFormField(widget=I18nTextInput, required=False)

    form = I18nTextInputForm(locales=["en"])

    assert isinstance(form.fields["name"].widget, I18nTextInput)


def test_pretalx_i18n_model_form_is_subclass():
    assert issubclass(PretalxI18nModelForm, PretalxI18nFormMixin)
