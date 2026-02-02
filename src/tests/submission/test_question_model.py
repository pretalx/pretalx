# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Natalia Katsiapi

import pytest
from django.db import IntegrityError
from django_scopes import scope

from pretalx.submission.models import Answer, AnswerOption, Question


@pytest.mark.parametrize("target", ("submission", "speaker", "reviewer"))
@pytest.mark.django_db
def test_missing_answers_submission_question(submission, target, question):
    with scope(event=submission.event):
        assert question.missing_answers() == 1
        assert (
            question.missing_answers(filter_talks=submission.event.submissions.all())
            == 1
        )
        question.target = target
        question.save()
        if target == "submission":
            Answer.objects.create(
                answer="True", submission=submission, question=question
            )
        elif target == "speaker":
            Answer.objects.create(
                answer="True", person=submission.speakers.first(), question=question
            )
        assert question.missing_answers() == 0


@pytest.mark.django_db
def test_question_required_property_optional_questions(question):
    assert question.required is False


@pytest.mark.django_db
def test_question_required_property_always_required_questions(question_required_always):
    assert question_required_always.required is True


@pytest.mark.django_db
def test_question_required_property_required_after_option_before_deadline(
    question_required_after_option_before_deadline,
):
    assert question_required_after_option_before_deadline.required is False


@pytest.mark.django_db
def test_question_required_property_required_after_option_after_deadline(
    question_required_after_option_after_deadline,
):
    assert question_required_after_option_after_deadline.required is True


@pytest.mark.django_db
def test_question_required_property_freeze_after_option_before_deadline_question_required_optional(
    question_freeze_after_option_before_deadline_question_required_optional,
):
    assert (
        question_freeze_after_option_before_deadline_question_required_optional.required
        is False
    )


@pytest.mark.django_db
def test_question_required_property_freeze_after_option_after_deadline_question_required_optional(
    question_freeze_after_option_after_deadline_question_required_optional,
):
    assert (
        question_freeze_after_option_after_deadline_question_required_optional.required
        is False
    )


@pytest.mark.django_db
def test_question_required_property_freeze_after_option_after_deadline_question_required(
    question_freeze_after_option_after_deadline_question_required_required,
):
    assert (
        question_freeze_after_option_after_deadline_question_required_required.required
        is False
    )


@pytest.mark.django_db
def test_question_required_property_freeze_after_option_before_deadline_question_required(
    question_freeze_after_option_before_deadline_question_required_required,
):
    assert (
        question_freeze_after_option_before_deadline_question_required_required.required
        is True
    )


@pytest.mark.django_db
def test_question_property_freeze_after_option_after_deadline(
    question_freeze_after_option_after_deadline,
):
    assert question_freeze_after_option_after_deadline.read_only is True


@pytest.mark.django_db
def test_question_property_freeze_after_option_before_deadline(
    question_freeze_after_option_before_deadline,
):
    assert question_freeze_after_option_before_deadline.read_only is False


@pytest.mark.django_db
def test_question_base_properties(submission, question):
    a = Answer.objects.create(answer="True", submission=submission, question=question)
    assert a.event == question.event
    assert str(a.question.question) in str(a.question)
    assert str(a.question.question) in str(a)


@pytest.mark.parametrize(
    "variant,answer,expected",
    (
        ("number", "1", "1"),
        ("string", "hm", "hm"),
        ("text", "", ""),
        ("boolean", "True", "Yes"),
        ("boolean", "False", "No"),
        ("boolean", "None", ""),
        ("file", "answer", ""),
        ("choices", "answer", ""),
        ("lol", "lol", None),
    ),
)
@pytest.mark.django_db
def test_answer_string_property(event, variant, answer, expected):
    with scope(event=event):
        question = Question.objects.create(question="?", variant=variant, event=event)
        answer = Answer.objects.create(question=question, answer=answer)
        assert answer.answer_string == expected


@pytest.mark.django_db
def test_question_identifier_auto_generated(event):
    with scope(event=event):
        question = Question.objects.create(
            question="Test?", variant="text", event=event
        )
        assert question.identifier is not None
        assert len(question.identifier) == 8


@pytest.mark.django_db
def test_question_identifier_custom(event):
    with scope(event=event):
        question = Question.objects.create(
            question="Test?", variant="text", event=event, identifier="MY-CUSTOM-ID"
        )
        assert question.identifier == "MY-CUSTOM-ID"


@pytest.mark.django_db(transaction=True)
def test_question_identifier_unique_per_event(event, other_event):
    with scope(event=event):
        Question.objects.create(
            question="Q1", variant="text", event=event, identifier="SAME-ID"
        )
        with pytest.raises(IntegrityError):
            Question.objects.create(
                question="Q2", variant="text", event=event, identifier="SAME-ID"
            )

    # Same identifier in different event should be allowed
    with scope(event=other_event):
        q = Question.objects.create(
            question="Q3", variant="text", event=other_event, identifier="SAME-ID"
        )
        assert q.identifier == "SAME-ID"


@pytest.mark.django_db
def test_answer_option_identifier_auto_generated(choice_question):
    with scope(event=choice_question.event):
        option = choice_question.options.first()
        assert option.identifier is not None
        assert len(option.identifier) == 8


@pytest.mark.django_db
def test_answer_option_identifier_custom(choice_question):
    with scope(event=choice_question.event):
        option = choice_question.options.create(
            answer="New Option", position=10, identifier="OPT-CUSTOM"
        )
        assert option.identifier == "OPT-CUSTOM"


@pytest.mark.django_db
def test_answer_option_identifier_unique_per_question(choice_question):
    with scope(event=choice_question.event):
        choice_question.options.create(
            answer="Option A", position=10, identifier="SAME-OPT"
        )
        with pytest.raises(IntegrityError):
            choice_question.options.create(
                answer="Option B", position=11, identifier="SAME-OPT"
            )


@pytest.mark.django_db
def test_generate_unique_codes_batch(choice_question):
    with scope(event=choice_question.event):
        # Generate 50 codes in one batch
        codes = AnswerOption.generate_unique_codes(50, question=choice_question)

        assert len(codes) == 50
        assert len(set(codes)) == 50  # All unique
        assert all(len(c) == 8 for c in codes)


@pytest.mark.parametrize(
    "target,related_attr",
    [
        ("submission", "submission"),
        ("speaker", "person"),
        ("reviewer", "review"),
    ],
)
@pytest.mark.django_db
def test_answer_file_path(event, submission, speaker, review, target, related_attr):
    from pretalx.submission.models.question import (
        QuestionTarget,
        QuestionVariant,
        answer_file_path,
    )

    with scope(event=event):
        question = Question.objects.create(
            event=event,
            question="Upload a file",
            variant=QuestionVariant.FILE,
            target=target,
        )

        answer = Answer(question=question, answer="")
        if target == QuestionTarget.SUBMISSION:
            answer.submission = submission
            expected_code = submission.code
        elif target == QuestionTarget.SPEAKER:
            answer.person = speaker
            expected_code = speaker.code
        elif target == QuestionTarget.REVIEWER:
            answer.review = review
            expected_code = f"r{review.pk}"

        path = answer_file_path(answer, "user_provided_name.pdf")

        assert path.startswith(f"{event.slug}/question_uploads/")
        assert f"q{question.pk}-{expected_code}_" in path
        assert path.endswith(".pdf")
        assert "user_provided_name" not in path
