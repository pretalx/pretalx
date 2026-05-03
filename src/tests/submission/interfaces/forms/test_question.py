# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django import forms

from pretalx.submission.interfaces.forms.question import (
    QuestionsForm,
    build_question_field,
)
from pretalx.submission.models import QuestionTarget, QuestionVariant
from tests.factories import (
    AnswerFactory,
    AnswerOptionFactory,
    EventFactory,
    QuestionFactory,
    ReviewFactory,
    SpeakerFactory,
    SubmissionFactory,
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
    only known after validation."""
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
    assert form.review == review


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
