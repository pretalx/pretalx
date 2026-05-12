# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt
import json

import pytest
from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.timezone import now

from pretalx.submission.interfaces.forms import (
    AnswerOptionForm,
    QuestionFilterForm,
    QuestionOrgaForm,
    ReminderFilterForm,
)
from pretalx.submission.interfaces.forms.question import (
    QuestionsForm,
    build_question_field,
)
from pretalx.submission.models import (
    QuestionTarget,
    QuestionVariant,
    SubmissionStates,
    SubmissionType,
)
from pretalx.submission.models.question import QuestionRequired
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    EventFactory,
    QuestionFactory,
    ReviewFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TrackFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_questions_form_init_loads_existing_answer():
    event = EventFactory()
    q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    submission = SubmissionFactory(event=event)
    answer = AnswerFactory(question=q, submission=submission, answer="42")

    form = QuestionsForm(event=event, submission=submission)

    field = form.fields[f"question_{q.pk}"]
    assert field.initial == "42"
    assert field.answer == answer


def test_questions_form_init_loads_file_answer_initial():
    event = EventFactory()
    q = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, variant=QuestionVariant.FILE
    )
    submission = SubmissionFactory(event=event)
    answer = AnswerFactory(question=q, submission=submission, answer="file://test.pdf")
    answer.answer_file.name = "test.pdf"
    answer.save()

    form = QuestionsForm(event=event, submission=submission)

    field = form.fields[f"question_{q.pk}"]
    assert field.initial == answer.answer_file


@pytest.mark.parametrize(
    ("prop_name", "included_target", "excluded_target"),
    (
        ("speaker_fields", QuestionTarget.SPEAKER, QuestionTarget.SUBMISSION),
        ("submission_fields", QuestionTarget.SUBMISSION, QuestionTarget.SPEAKER),
    ),
)
def test_questions_form_fields_property_filters_by_target(
    prop_name, included_target, excluded_target
):
    event = EventFactory()
    included_q = QuestionFactory(event=event, target=included_target)
    excluded_q = QuestionFactory(event=event, target=excluded_target)

    form = QuestionsForm(event=event, target=None)

    field_names = [f.name for f in getattr(form, prop_name)]
    assert f"question_{included_q.pk}" in field_names
    assert f"question_{excluded_q.pk}" not in field_names


def test_questions_form_serialize_answers_with_existing_answer():
    event = EventFactory()
    q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    submission = SubmissionFactory(event=event)
    AnswerFactory(question=q, submission=submission, answer="My answer")

    form = QuestionsForm(event=event, submission=submission)

    serialized = form.serialize_answers()
    assert serialized[f"question-{q.pk}"] == "My answer"


def test_questions_form_serialize_answers_without_answer():
    event = EventFactory()
    q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)

    form = QuestionsForm(event=event)

    serialized = form.serialize_answers()
    assert serialized[f"question-{q.pk}"] is None


def test_questions_form_save_creates_answer():
    event = EventFactory()
    q = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, variant=QuestionVariant.STRING
    )
    submission = SubmissionFactory(event=event)

    form = QuestionsForm(
        event=event, submission=submission, data={f"question_{q.pk}": "New answer"}
    )
    assert form.is_valid(), form.errors
    form.save()

    answer = submission.answers.get(question=q)

    assert answer.answer == "New answer"


def test_questions_form_save_updates_existing_answer():
    event = EventFactory()
    q = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, variant=QuestionVariant.STRING
    )
    submission = SubmissionFactory(event=event)
    AnswerFactory(question=q, submission=submission, answer="Old answer")

    form = QuestionsForm(
        event=event, submission=submission, data={f"question_{q.pk}": "Updated answer"}
    )
    assert form.is_valid(), form.errors
    form.save()

    answer = submission.answers.get(question=q)

    assert answer.answer == "Updated answer"


def test_questions_form_save_deletes_answer_when_empty():
    event = EventFactory()
    q = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, variant=QuestionVariant.STRING
    )
    submission = SubmissionFactory(event=event)
    AnswerFactory(question=q, submission=submission, answer="Old answer")

    form = QuestionsForm(
        event=event, submission=submission, data={f"question_{q.pk}": ""}
    )
    assert form.is_valid(), form.errors
    form.save()

    assert not submission.answers.filter(question=q).exists()


def test_questions_form_save_choice_question():
    event = EventFactory()
    q = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, variant=QuestionVariant.CHOICES
    )
    option = AnswerOptionFactory(question=q)
    submission = SubmissionFactory(event=event)

    form = QuestionsForm(
        event=event, submission=submission, data={f"question_{q.pk}": str(option.pk)}
    )
    assert form.is_valid(), form.errors
    form.save()

    answer = submission.answers.get(question=q)

    assert answer.answer == option.answer
    assert list(answer.options.all()) == [option]


def test_questions_form_save_multiple_choice_question():
    event = EventFactory()
    q = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, variant=QuestionVariant.MULTIPLE
    )
    opt1 = AnswerOptionFactory(question=q)
    opt2 = AnswerOptionFactory(question=q)
    submission = SubmissionFactory(event=event)

    form = QuestionsForm(
        event=event,
        submission=submission,
        data={f"question_{q.pk}": [str(opt1.pk), str(opt2.pk)]},
    )
    assert form.is_valid(), form.errors
    form.save()

    answer = submission.answers.get(question=q)

    assert set(answer.options.all()) == {opt1, opt2}


def test_questions_form_save_boolean_question():
    event = EventFactory()
    q = QuestionFactory(
        event=event, target=QuestionTarget.SUBMISSION, variant=QuestionVariant.BOOLEAN
    )
    submission = SubmissionFactory(event=event)

    form = QuestionsForm(
        event=event, submission=submission, data={f"question_{q.pk}": "True"}
    )
    assert form.is_valid(), form.errors
    form.save()

    answer = submission.answers.get(question=q)

    assert answer.answer == "True"


def test_questions_form_init_uses_default_answer():
    event = EventFactory()
    q = QuestionFactory(
        event=event,
        target=QuestionTarget.SUBMISSION,
        variant=QuestionVariant.STRING,
        default_answer="Default value",
    )

    form = QuestionsForm(event=event)

    field = form.fields[f"question_{q.pk}"]
    assert field.initial == "Default value"


def test_questions_form_init_read_only_disables_fields():
    event = EventFactory()
    QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)

    form = QuestionsForm(event=event, read_only=True)

    for field in form.fields.values():
        assert field.disabled is True


def test_questions_form_init_track_from_submission():
    """When no track is explicitly provided, submission.track is used."""
    event = EventFactory()
    track = TrackFactory(event=event)
    submission = SubmissionFactory(event=event, track=track)
    track_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    track_q.tracks.add(track)
    other_track = TrackFactory(event=event)
    other_q = QuestionFactory(event=event, target=QuestionTarget.SUBMISSION)
    other_q.tracks.add(other_track)

    form = QuestionsForm(event=event, submission=submission)

    assert f"question_{track_q.pk}" in form.fields
    assert f"question_{other_q.pk}" not in form.fields


def test_questions_form_save_speaker_question():
    event = EventFactory()
    q = QuestionFactory(
        event=event, target=QuestionTarget.SPEAKER, variant=QuestionVariant.STRING
    )
    speaker = SpeakerFactory(event=event)

    form = QuestionsForm(
        event=event,
        speaker=speaker,
        target=QuestionTarget.SPEAKER,
        data={f"question_{q.pk}": "Speaker answer"},
    )
    assert form.is_valid(), form.errors
    form.save()

    answer = speaker.answers.get(question=q)

    assert answer.answer == "Speaker answer"


def test_questions_form_save_reviewer_question():
    event = EventFactory()
    q = QuestionFactory(
        event=event, target=QuestionTarget.REVIEWER, variant=QuestionVariant.STRING
    )
    review = ReviewFactory(submission__event=event)

    form = QuestionsForm(
        event=event,
        review=review,
        target=QuestionTarget.REVIEWER,
        data={f"question_{q.pk}": "Reviewer answer"},
    )
    assert form.is_valid(), form.errors
    form.save()

    answer = review.answers.get(question=q)

    assert answer.answer == "Reviewer answer"


def test_questions_form_save_accepts_review_override():
    """``save(review=...)`` lets callers attach answers to a review that was
    only known after validation. The form's ``review`` attribute is not
    mutated by the call."""
    event = EventFactory()
    q = QuestionFactory(
        event=event, target=QuestionTarget.REVIEWER, variant=QuestionVariant.STRING
    )
    review = ReviewFactory(submission__event=event)

    form = QuestionsForm(
        event=event,
        target=QuestionTarget.REVIEWER,
        data={f"question_{q.pk}": "Late-bound review"},
    )
    assert form.is_valid(), form.errors
    form.save(review=review)

    answer = review.answers.get(question=q)
    assert answer.answer == "Late-bound review"
    assert form.review is None


def test_questions_form_save_raises_without_required_target():
    """If a question's target object is missing entirely (neither passed at
    __init__ nor at save), ``save()`` raises instead of silently no-op'ing
    on the polymorphic FK assignment."""
    event = EventFactory()
    q = QuestionFactory(
        event=event, target=QuestionTarget.SPEAKER, variant=QuestionVariant.STRING
    )

    form = QuestionsForm(
        event=event,
        target=QuestionTarget.SPEAKER,
        data={f"question_{q.pk}": "Speaker answer"},
    )
    assert form.is_valid(), form.errors
    with pytest.raises(ValueError, match="no speaker target object"):
        form.save()


def test_build_question_field_boolean():
    question = QuestionFactory(
        variant=QuestionVariant.BOOLEAN, question_required="required"
    )

    field = build_question_field(question=question)

    assert isinstance(field, forms.BooleanField)
    assert field.required is True


def test_build_question_field_boolean_with_initial_true():
    question = QuestionFactory(variant=QuestionVariant.BOOLEAN)
    submission = SubmissionFactory(event=question.event)
    AnswerFactory(question=question, submission=submission, answer="True")

    field = build_question_field(question=question, target_object=submission)

    assert field.initial is True


def test_build_question_field_number():
    question = QuestionFactory(
        variant=QuestionVariant.NUMBER, min_number=1, max_number=100
    )
    submission = SubmissionFactory(event=question.event)
    AnswerFactory(question=question, submission=submission, answer="42")

    field = build_question_field(question=question, target_object=submission)

    assert isinstance(field, forms.DecimalField)
    assert field.min_value == 1
    assert field.max_value == 100
    assert field.initial == "42"


def test_build_question_field_string_with_char_counting():
    question = QuestionFactory(
        variant=QuestionVariant.STRING, min_length=10, max_length=200
    )

    field = build_question_field(question=question)

    assert isinstance(field, forms.CharField)
    assert field.widget.attrs.get("data-minlength") == 10
    assert field.widget.attrs.get("data-maxlength") == 200


def test_build_question_field_string_with_word_counting():
    event = EventFactory(cfp__settings={"count_length_in": "words"})
    question = QuestionFactory(
        event=event, variant=QuestionVariant.STRING, min_length=5, max_length=50
    )

    field = build_question_field(question=question)

    assert isinstance(field, forms.CharField)
    assert "data-minlength" not in field.widget.attrs
    assert "data-maxlength" not in field.widget.attrs


def test_build_question_field_string_without_length_constraints():
    question = QuestionFactory(variant=QuestionVariant.STRING)

    field = build_question_field(question=question)

    assert isinstance(field, forms.CharField)
    assert "data-minlength" not in field.widget.attrs
    assert "data-maxlength" not in field.widget.attrs


def test_build_question_field_url():
    question = QuestionFactory(variant=QuestionVariant.URL)
    submission = SubmissionFactory(event=question.event)
    AnswerFactory(
        question=question, submission=submission, answer="https://example.com"
    )

    field = build_question_field(question=question, target_object=submission)

    assert isinstance(field, forms.URLField)
    assert field.initial == "https://example.com"


def test_build_question_field_text_with_char_counting():
    question = QuestionFactory(
        variant=QuestionVariant.TEXT, min_length=20, max_length=500
    )

    field = build_question_field(question=question)

    assert isinstance(field, forms.CharField)
    assert isinstance(field.widget, forms.Textarea)
    assert field.widget.attrs.get("data-minlength") == 20
    assert field.widget.attrs.get("data-maxlength") == 500


def test_build_question_field_text_with_word_counting():
    event = EventFactory(cfp__settings={"count_length_in": "words"})
    question = QuestionFactory(
        event=event, variant=QuestionVariant.TEXT, min_length=5, max_length=100
    )

    field = build_question_field(question=question)

    assert isinstance(field, forms.CharField)
    assert "data-minlength" not in field.widget.attrs
    assert "data-maxlength" not in field.widget.attrs


def test_build_question_field_text_without_length_constraints():
    question = QuestionFactory(variant=QuestionVariant.TEXT)

    field = build_question_field(question=question)

    assert isinstance(field, forms.CharField)
    assert isinstance(field.widget, forms.Textarea)
    assert "data-minlength" not in field.widget.attrs
    assert "data-maxlength" not in field.widget.attrs


def test_build_question_field_file():
    question = QuestionFactory(variant=QuestionVariant.FILE)

    field = build_question_field(question=question)

    assert isinstance(field, forms.FileField)


def test_build_question_field_choices():
    question = QuestionFactory(variant=QuestionVariant.CHOICES)
    opt1 = AnswerOptionFactory(question=question, answer="Option A")
    opt2 = AnswerOptionFactory(question=question, answer="Option B")

    field = build_question_field(question=question)

    assert isinstance(field, forms.ModelChoiceField)
    assert set(field.queryset) == {opt1, opt2}


def test_build_question_field_multiple():
    question = QuestionFactory(variant=QuestionVariant.MULTIPLE)
    opt1 = AnswerOptionFactory(question=question, answer="Option A")
    opt2 = AnswerOptionFactory(question=question, answer="Option B")

    field = build_question_field(question=question)

    assert isinstance(field, forms.ModelMultipleChoiceField)
    assert set(field.queryset) == {opt1, opt2}


def test_build_question_field_date_with_constraints():
    question = QuestionFactory(
        variant=QuestionVariant.DATE,
        min_date=dt.date(2025, 1, 1),
        max_date=dt.date(2025, 12, 31),
    )

    field = build_question_field(question=question)

    assert isinstance(field, forms.DateField)
    assert field.widget.attrs.get("data-date-start-date") == "2025-01-01"
    assert field.widget.attrs.get("data-date-end-date") == "2025-12-31"
    assert len(field.validators) == 2


def test_build_question_field_date_with_initial():
    question = QuestionFactory(variant=QuestionVariant.DATE)
    submission = SubmissionFactory(event=question.event)
    AnswerFactory(question=question, submission=submission, answer="2025-06-15")

    field = build_question_field(question=question, target_object=submission)

    assert field.initial == dt.date(2025, 6, 15)


def test_build_question_field_datetime_with_constraints():
    min_dt = dt.datetime(2025, 1, 1, 0, 0, tzinfo=dt.UTC)
    max_dt = dt.datetime(2025, 12, 31, 23, 59, tzinfo=dt.UTC)
    question = QuestionFactory(
        variant=QuestionVariant.DATETIME, min_datetime=min_dt, max_datetime=max_dt
    )

    field = build_question_field(question=question)

    assert isinstance(field, forms.DateTimeField)
    assert field.widget.attrs.get("min") == min_dt.isoformat()
    assert field.widget.attrs.get("max") == max_dt.isoformat()
    assert len(field.validators) == 2


def test_build_question_field_datetime_with_initial():
    question = QuestionFactory(variant=QuestionVariant.DATETIME)
    submission = SubmissionFactory(event=question.event)
    AnswerFactory(
        question=question, submission=submission, answer="2025-06-15T10:30:00+00:00"
    )

    field = build_question_field(question=question, target_object=submission)

    expected = dt.datetime(2025, 6, 15, 10, 30, tzinfo=dt.UTC).astimezone(
        question.event.tz
    )
    assert field.initial == expected


def test_build_question_field_read_only_via_freeze():
    question = QuestionFactory(
        variant=QuestionVariant.STRING,
        freeze_after=dt.datetime(2020, 1, 1, tzinfo=dt.UTC),
    )

    field = build_question_field(question=question)

    assert field.disabled is True


def test_build_question_field_read_only_param():
    question = QuestionFactory(variant=QuestionVariant.STRING)

    field = build_question_field(question=question, read_only=True)

    assert field.disabled is True


def test_build_question_field_date_no_constraints():
    question = QuestionFactory(variant=QuestionVariant.DATE)

    field = build_question_field(question=question)

    assert isinstance(field, forms.DateField)
    assert "data-date-start-date" not in field.widget.attrs
    assert "data-date-end-date" not in field.widget.attrs


def test_build_question_field_datetime_no_constraints():
    question = QuestionFactory(variant=QuestionVariant.DATETIME)

    field = build_question_field(question=question)

    assert isinstance(field, forms.DateTimeField)
    assert "min" not in field.widget.attrs
    assert "max" not in field.widget.attrs


def test_build_question_field_choices_with_initial_object():
    question = QuestionFactory(variant=QuestionVariant.CHOICES)
    opt = AnswerOptionFactory(question=question, answer="Selected")
    AnswerOptionFactory(question=question, answer="Other")
    submission = SubmissionFactory(event=question.event)
    answer = AnswerFactory(question=question, submission=submission)
    answer.options.add(opt)

    field = build_question_field(question=question, target_object=submission)

    assert field.initial == opt


def test_build_question_field_multiple_with_initial_object():
    question = QuestionFactory(variant=QuestionVariant.MULTIPLE)
    opt1 = AnswerOptionFactory(question=question, answer="A")
    opt2 = AnswerOptionFactory(question=question, answer="B")
    submission = SubmissionFactory(event=question.event)
    answer = AnswerFactory(question=question, submission=submission)
    answer.options.add(opt1, opt2)

    field = build_question_field(question=question, target_object=submission)

    assert set(field.initial) == {opt1, opt2}


def test_question_orga_form_init_removes_tracks_when_not_configured():
    event = EventFactory(feature_flags={"use_tracks": False})

    form = QuestionOrgaForm(event=event, locales=event.locales)

    assert "tracks" not in form.fields


def test_question_orga_form_init_removes_tracks_when_no_tracks_exist():
    event = EventFactory(feature_flags={"use_tracks": True})

    form = QuestionOrgaForm(event=event, locales=event.locales)

    assert "tracks" not in form.fields


def test_question_orga_form_init_shows_tracks_when_configured():
    event = EventFactory(feature_flags={"use_tracks": True})
    track = TrackFactory(event=event)

    form = QuestionOrgaForm(event=event, locales=event.locales)

    assert "tracks" in form.fields
    assert track in form.fields["tracks"].queryset


def test_question_orga_form_init_keeps_submission_types_when_they_exist():
    event = EventFactory()

    form = QuestionOrgaForm(event=event, locales=event.locales)

    assert "submission_types" in form.fields


def test_question_orga_form_init_sets_submission_types_queryset():
    event = EventFactory()
    extra_type = SubmissionTypeFactory(event=event)

    form = QuestionOrgaForm(event=event, locales=event.locales)

    assert "submission_types" in form.fields
    assert extra_type in form.fields["submission_types"].queryset


def test_question_orga_form_init_removes_submission_types_when_none_exist():
    event = EventFactory()
    other_event = EventFactory()
    SubmissionType.objects.filter(event=event).update(event=other_event)

    form = QuestionOrgaForm(event=event, locales=event.locales)

    assert "submission_types" not in form.fields


def test_question_orga_form_clean_options_plain_text():
    event = EventFactory()
    content = b"Option A\nOption B\nOption C\n"
    upload = SimpleUploadedFile("options.txt", content, content_type="text/plain")

    form = QuestionOrgaForm(
        data={
            "target": "submission",
            "question_0": "Pick one",
            "variant": QuestionVariant.CHOICES,
            "question_required": QuestionRequired.OPTIONAL,
            "contains_personal_data": False,
        },
        files={"options": upload},
        event=event,
        locales=event.locales,
    )
    form.is_valid()

    assert form.cleaned_data["options"] == ["Option A", "Option B", "Option C"]


def test_question_orga_form_clean_options_json():
    event = EventFactory()
    data = [{"en": "English", "de": "Deutsch"}, {"en": "Yes", "de": "Ja"}]
    content = json.dumps(data).encode()
    upload = SimpleUploadedFile("opts.json", content, content_type="application/json")

    form = QuestionOrgaForm(
        data={
            "target": "submission",
            "question_0": "Pick one",
            "variant": QuestionVariant.CHOICES,
            "question_required": QuestionRequired.OPTIONAL,
            "contains_personal_data": False,
        },
        files={"options": upload},
        event=event,
        locales=event.locales,
    )
    form.is_valid()

    options = form.cleaned_data["options"]
    assert len(options) == 2
    assert options[0].data == {"en": "English", "de": "Deutsch"}


def test_question_orga_form_clean_options_invalid_file():
    event = EventFactory()
    upload = SimpleUploadedFile(
        "bad.bin", b"\x80\x81\x82", content_type="application/octet-stream"
    )

    form = QuestionOrgaForm(
        data={
            "target": "submission",
            "question_0": "Pick one",
            "variant": QuestionVariant.CHOICES,
            "question_required": QuestionRequired.OPTIONAL,
            "contains_personal_data": False,
        },
        files={"options": upload},
        event=event,
        locales=event.locales,
    )
    form.is_valid()

    assert "options" in form.errors


def test_question_orga_form_clean_options_json_not_list():
    event = EventFactory()
    content = json.dumps({"key": "value"}).encode()
    upload = SimpleUploadedFile("bad.json", content, content_type="application/json")

    form = QuestionOrgaForm(
        data={
            "target": "submission",
            "question_0": "Pick one",
            "variant": QuestionVariant.CHOICES,
            "question_required": QuestionRequired.OPTIONAL,
            "contains_personal_data": False,
        },
        files={"options": upload},
        event=event,
        locales=event.locales,
    )
    form.is_valid()

    assert len(form.cleaned_data["options"]) == 1


def test_question_orga_form_clean_options_json_list_of_non_dicts():
    event = EventFactory()
    content = json.dumps(["Option A", "Option B"]).encode()
    upload = SimpleUploadedFile("opts.json", content, content_type="application/json")

    form = QuestionOrgaForm(
        data={
            "target": "submission",
            "question_0": "Pick one",
            "variant": QuestionVariant.CHOICES,
            "question_required": QuestionRequired.OPTIONAL,
            "contains_personal_data": False,
        },
        files={"options": upload},
        event=event,
        locales=event.locales,
    )
    form.is_valid()

    assert form.cleaned_data["options"] == ['["Option A", "Option B"]']


def test_question_orga_form_clean_options_empty_file():
    event = EventFactory()

    form = QuestionOrgaForm(
        data={
            "target": "submission",
            "question_0": "Pick one",
            "variant": QuestionVariant.CHOICES,
            "question_required": QuestionRequired.OPTIONAL,
            "contains_personal_data": False,
        },
        event=event,
        locales=event.locales,
    )
    form.is_valid()

    assert form.cleaned_data.get("options") is None


def test_question_orga_form_clean_after_deadline_requires_deadline():
    """``Question.clean()`` enforces ``AFTER_DEADLINE`` requires a deadline; the
    form picks it up via full_clean."""
    event = EventFactory()

    form = QuestionOrgaForm(
        data={
            "target": "submission",
            "question_0": "Pick one",
            "variant": QuestionVariant.STRING,
            "question_required": QuestionRequired.AFTER_DEADLINE,
            "deadline": "",
            "contains_personal_data": False,
        },
        event=event,
        locales=event.locales,
    )
    valid = form.is_valid()

    assert not valid
    assert "deadline" in form.errors


@pytest.mark.parametrize(
    "question_required",
    (QuestionRequired.REQUIRED, QuestionRequired.OPTIONAL),
    ids=["required", "optional"],
)
def test_question_orga_form_clean_required_or_optional_clears_deadline(
    question_required,
):
    event = EventFactory()

    form = QuestionOrgaForm(
        data={
            "target": "submission",
            "question_0": "Pick one",
            "variant": QuestionVariant.STRING,
            "question_required": question_required,
            "deadline": now().isoformat(),
            "contains_personal_data": False,
        },
        event=event,
        locales=event.locales,
    )
    form.is_valid()

    assert form.cleaned_data["deadline"] is None


def test_question_orga_form_clean_replace_without_options_is_error():
    event = EventFactory()

    form = QuestionOrgaForm(
        data={
            "target": "submission",
            "question_0": "Pick one",
            "variant": QuestionVariant.CHOICES,
            "question_required": QuestionRequired.OPTIONAL,
            "options_replace": True,
            "contains_personal_data": False,
        },
        event=event,
        locales=event.locales,
    )
    valid = form.is_valid()

    assert not valid
    assert "options_replace" in form.errors


def test_question_orga_form_clean_public_clears_limit_teams():
    event = EventFactory()

    form = QuestionOrgaForm(
        data={
            "target": "submission",
            "question_0": "Pick one",
            "variant": QuestionVariant.STRING,
            "question_required": QuestionRequired.OPTIONAL,
            "is_public": True,
            "contains_personal_data": False,
        },
        event=event,
        locales=event.locales,
    )
    form.is_valid()

    assert "limit_teams" not in form.cleaned_data


def test_question_orga_form_clean_identifier_validates_uniqueness():
    event = EventFactory()
    QuestionFactory(event=event, identifier="MY-ID")

    form = QuestionOrgaForm(
        data={
            "target": "submission",
            "question_0": "Another question",
            "variant": QuestionVariant.STRING,
            "question_required": QuestionRequired.OPTIONAL,
            "identifier": "MY-ID",
            "contains_personal_data": False,
        },
        event=event,
        locales=event.locales,
    )
    valid = form.is_valid()

    assert not valid
    assert "identifier" in form.errors


def test_question_orga_form_clean_identifier_allows_same_instance():
    event = EventFactory()
    question = QuestionFactory(event=event, identifier="MY-ID")

    form = QuestionOrgaForm(
        data={
            "target": "submission",
            "question_0": "Updated question",
            "variant": QuestionVariant.STRING,
            "question_required": QuestionRequired.OPTIONAL,
            "identifier": "MY-ID",
            "contains_personal_data": False,
        },
        instance=question,
        event=event,
        locales=event.locales,
    )
    valid = form.is_valid()

    assert valid, form.errors


def test_question_orga_form_save_without_options_returns_instance():
    event = EventFactory()
    question = QuestionFactory(event=event, variant=QuestionVariant.STRING)

    form = QuestionOrgaForm(
        data={
            "target": "submission",
            "question_0": "Updated text",
            "variant": QuestionVariant.STRING,
            "question_required": QuestionRequired.OPTIONAL,
            "contains_personal_data": False,
        },
        instance=question,
        event=event,
        locales=event.locales,
    )
    assert form.is_valid(), form.errors
    result = form.save()

    assert result.pk == question.pk


def test_question_orga_form_save_creates_options_with_replace():
    """Saving with replace=True deletes old options/answers and creates new ones."""
    event = EventFactory()
    question = QuestionFactory(event=event, variant=QuestionVariant.CHOICES)
    old_option = AnswerOptionFactory(question=question, answer="Old")
    AnswerFactory(question=question, answer="Old")

    content = b"New A\nNew B\n"
    upload = SimpleUploadedFile("options.txt", content, content_type="text/plain")

    form = QuestionOrgaForm(
        data={
            "target": "submission",
            "question_0": str(question.question),
            "variant": QuestionVariant.CHOICES,
            "question_required": QuestionRequired.OPTIONAL,
            "options_replace": True,
            "contains_personal_data": False,
        },
        files={"options": upload},
        instance=question,
        event=event,
        locales=event.locales,
    )
    assert form.is_valid(), form.errors
    form.save()

    options = list(
        question.options.order_by("position").values_list("answer", flat=True)
    )
    assert options == ["New A", "New B"]
    assert question.answers.count() == 0
    assert not question.options.filter(pk=old_option.pk).exists()


def test_answer_option_form_valid_with_answer():
    question = QuestionFactory(variant=QuestionVariant.CHOICES)
    form = AnswerOptionForm(
        data={"answer_0": "My option"}, locales=question.event.locales
    )

    assert form.is_valid(), form.errors


def test_question_filter_form_init_sets_submission_type_queryset():
    event = EventFactory()
    stype = event.cfp.default_type

    form = QuestionFilterForm(event=event)

    assert stype in form.fields["submission_type"].queryset


def test_question_filter_form_hides_track_when_disabled():
    event = EventFactory(feature_flags={"use_tracks": False})

    form = QuestionFilterForm(event=event)

    assert "track" not in form.fields


def test_question_filter_form_shows_track_when_enabled():
    event = EventFactory(feature_flags={"use_tracks": True})
    track = TrackFactory(event=event)

    form = QuestionFilterForm(event=event)

    assert "track" in form.fields
    assert track in form.fields["track"].queryset


def test_question_filter_form_get_submissions_no_filter():
    event = EventFactory()
    sub1 = SubmissionFactory(event=event)
    sub2 = SubmissionFactory(event=event)

    form = QuestionFilterForm(data={"role": "", "submission_type": ""}, event=event)
    assert form.is_valid(), form.errors
    talks = form.get_submissions()

    assert set(talks) == {sub1, sub2}


def test_question_filter_form_get_submissions_accepted_role():
    """``accepted`` includes accepted + confirmed (driven by ``SubmissionStates.accepted_states``)."""
    event = EventFactory()
    accepted = SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    confirmed = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    SubmissionFactory(event=event, state=SubmissionStates.SUBMITTED)

    form = QuestionFilterForm(
        data={"role": "accepted", "submission_type": ""}, event=event
    )
    assert form.is_valid(), form.errors
    talks = form.get_submissions()

    assert set(talks) == {accepted, confirmed}


def test_question_filter_form_get_submissions_confirmed_role():
    event = EventFactory()
    confirmed = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
    SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)

    form = QuestionFilterForm(
        data={"role": "confirmed", "submission_type": ""}, event=event
    )
    assert form.is_valid(), form.errors
    talks = form.get_submissions()

    assert list(talks) == [confirmed]


def test_question_filter_form_get_submissions_by_track():
    event = EventFactory(feature_flags={"use_tracks": True})
    track = TrackFactory(event=event)
    on_track = SubmissionFactory(event=event, track=track)
    SubmissionFactory(event=event)

    form = QuestionFilterForm(
        data={"role": "", "submission_type": "", "track": track.pk}, event=event
    )
    assert form.is_valid(), form.errors
    talks = form.get_submissions()

    assert list(talks) == [on_track]


def test_question_filter_form_get_submissions_by_submission_type():
    event = EventFactory()
    stype = SubmissionTypeFactory(event=event)
    matching = SubmissionFactory(event=event, submission_type=stype)
    SubmissionFactory(event=event)

    form = QuestionFilterForm(
        data={"role": "", "submission_type": stype.pk}, event=event
    )
    assert form.is_valid(), form.errors
    talks = form.get_submissions()

    assert list(talks) == [matching]


def test_question_filter_form_get_question_information_text_variant():
    event = EventFactory()
    question = QuestionFactory(event=event, target="submission")
    sub = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    sub.speakers.add(speaker)
    AnswerFactory(question=question, submission=sub, answer="yes")

    form = QuestionFilterForm(data={"role": "", "submission_type": ""}, event=event)
    assert form.is_valid(), form.errors
    info = form.get_question_information(question)

    assert info["answer_count"] == 1
    grouped = list(info["grouped_answers"])
    assert len(grouped) == 1
    assert grouped[0]["answer"] == "yes"
    assert grouped[0]["count"] == 1


def test_question_filter_form_get_question_information_grouped_choices():
    event = EventFactory()
    question = QuestionFactory(
        event=event, target="submission", variant=QuestionVariant.CHOICES
    )
    opt = AnswerOptionFactory(question=question, answer="Option A")
    sub = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    sub.speakers.add(speaker)
    answer = AnswerFactory(question=question, submission=sub, answer="Option A")
    answer.options.add(opt)

    form = QuestionFilterForm(data={"role": "", "submission_type": ""}, event=event)
    assert form.is_valid(), form.errors
    info = form.get_question_information(question)

    assert info["answer_count"] == 1
    grouped = list(info["grouped_answers"])
    assert len(grouped) == 1
    assert grouped[0]["count"] == 1


def test_question_filter_form_get_question_information_file_variant():
    event = EventFactory()
    question = QuestionFactory(
        event=event, target="submission", variant=QuestionVariant.FILE
    )
    sub = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    sub.speakers.add(speaker)
    AnswerFactory(question=question, submission=sub, answer="file://test.pdf")

    form = QuestionFilterForm(data={"role": "", "submission_type": ""}, event=event)
    assert form.is_valid(), form.errors
    info = form.get_question_information(question)

    assert info["answer_count"] == 1
    grouped = list(info["grouped_answers"])
    assert len(grouped) == 1
    assert grouped[0]["count"] == 1


def test_reminder_filter_form_questions_queryset_excludes_frozen():
    event = EventFactory()
    active_q = QuestionFactory(event=event, target="submission", freeze_after=None)
    QuestionFactory(
        event=event, target="submission", freeze_after=now() - dt.timedelta(days=1)
    )

    form = ReminderFilterForm(event=event)

    qs = form.fields["questions"].queryset
    assert active_q in qs
    assert qs.count() == 1


def test_reminder_filter_form_inherits_track_filtering():
    event = EventFactory(feature_flags={"use_tracks": False})

    form = ReminderFilterForm(event=event)

    assert "track" not in form.fields


def test_reminder_filter_form_includes_speaker_and_submission_questions():
    event = EventFactory()
    sub_q = QuestionFactory(event=event, target="submission")
    spk_q = QuestionFactory(event=event, target="speaker")
    QuestionFactory(event=event, target="reviewer")

    form = ReminderFilterForm(event=event)

    qs = form.fields["questions"].queryset
    assert sub_q in qs
    assert spk_q in qs
    assert qs.count() == 2
