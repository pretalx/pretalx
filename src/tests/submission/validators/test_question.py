# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.submission.enums import QuestionRequired
from pretalx.submission.validators.question import (
    validate_answer_option_identifier_unique,
    validate_question_deadline,
    validate_question_identifier_unique,
)
from tests.factories import AnswerOptionFactory, EventFactory, QuestionFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_validate_question_identifier_unique_raises_on_duplicate():
    event = EventFactory()
    QuestionFactory(event=event, identifier="DUPE-ID")

    with pytest.raises(ValidationError) as exc_info:
        validate_question_identifier_unique(event=event, identifier="DUPE-ID")

    assert "identifier" in exc_info.value.message_dict


def test_validate_question_identifier_unique_case_insensitive():
    event = EventFactory()
    QuestionFactory(event=event, identifier="My-Id")

    with pytest.raises(ValidationError):
        validate_question_identifier_unique(event=event, identifier="my-id")


def test_validate_question_identifier_unique_allows_same_instance():
    event = EventFactory()
    question = QuestionFactory(event=event, identifier="MY-ID")
    validate_question_identifier_unique(
        event=event, identifier="MY-ID", instance=question
    )


@pytest.mark.parametrize("identifier", ("", None), ids=("empty", "none"))
def test_validate_question_identifier_unique_returns_early_for_falsy(identifier):
    validate_question_identifier_unique(event=EventFactory(), identifier=identifier)


def test_validate_answer_option_identifier_unique_raises_on_duplicate():
    option = AnswerOptionFactory(identifier="DUPE")
    with pytest.raises(ValidationError) as exc_info:
        validate_answer_option_identifier_unique(
            question=option.question, identifier="DUPE"
        )

    assert "identifier" in exc_info.value.message_dict


def test_validate_answer_option_identifier_unique_case_insensitive():
    option = AnswerOptionFactory(identifier="MyOpt")
    with pytest.raises(ValidationError):
        validate_answer_option_identifier_unique(
            question=option.question, identifier="myopt"
        )


def test_validate_answer_option_identifier_unique_allows_same_instance():
    option = AnswerOptionFactory(identifier="MY-OPT")
    validate_answer_option_identifier_unique(
        question=option.question, identifier="MY-OPT", instance=option
    )


@pytest.mark.parametrize("identifier", ("", None), ids=("empty", "none"))
def test_validate_answer_option_identifier_unique_returns_early_for_falsy(identifier):
    validate_answer_option_identifier_unique(
        question=QuestionFactory(), identifier=identifier
    )


def test_validate_question_deadline_required_after_deadline_without_deadline():
    question = QuestionFactory.build(
        question_required=QuestionRequired.AFTER_DEADLINE, deadline=None
    )
    with pytest.raises(ValidationError) as exc_info:
        validate_question_deadline(question)

    assert "deadline" in exc_info.value.message_dict


def test_validate_question_deadline_optional_does_not_require_deadline():
    question = QuestionFactory.build(
        question_required=QuestionRequired.OPTIONAL, deadline=None
    )
    validate_question_deadline(question)
