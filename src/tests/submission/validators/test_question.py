# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.submission.enums import QuestionRequired, QuestionVariant
from pretalx.submission.validators.question import (
    get_option_count_help_text,
    validate_answer_option_identifier_unique,
    validate_option_count,
    validate_question_deadline,
    validate_question_identifier_unique,
    validate_question_min_options_available,
    validate_question_option_limits,
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


@pytest.mark.parametrize(
    ("text", "min_number", "max_number", "expected"),
    (
        ("existing", None, None, "existing"),
        ("", 2, 5, "Please select between 2 and 5 options."),
        ("", 3, 3, "Please select exactly 3 options."),
        ("", 2, None, "Please select at least 2 options."),
        ("", None, 5, "Please select at most 5 options."),
        ("Base.", 1, 3, "Base. Please select between 1 and 3 options."),
    ),
    ids=("no_limits", "min_max", "exact", "min_only", "max_only", "prepends_existing"),
)
def test_get_option_count_help_text(text, min_number, max_number, expected):
    assert get_option_count_help_text(text, min_number, max_number) == expected


@pytest.mark.parametrize(
    ("value", "min_number", "max_number"),
    ((["a", "b"], 1, 5), (["a", "b", "c"], 3, 3), ([], None, 5), (["a"], None, None)),
    ids=("in_range", "exact", "empty_under_max", "no_limits"),
)
def test_validate_option_count_accepts_valid(value, min_number, max_number):
    validate_option_count(value, min_number, max_number)


@pytest.mark.parametrize(
    ("value", "min_number", "max_number", "expected"),
    (
        (["a"], 3, 5, "Please select between 3 and 5 options. You selected 1 options."),
        (
            ["a", "b", "c", "d"],
            None,
            3,
            "Please select at most 3 options. You selected 4 options.",
        ),
        (None, 2, None, "Please select at least 2 options. You selected 0 options."),
    ),
    ids=("too_few", "too_many", "none_below_min"),
)
def test_validate_option_count_rejects_invalid(value, min_number, max_number, expected):
    with pytest.raises(ValidationError) as exc_info:
        validate_option_count(value, min_number, max_number)

    assert exc_info.value.messages == [expected]


def test_validate_question_option_limits_rejects_min_above_max():
    question = QuestionFactory.build(min_options=3, max_options=2)

    with pytest.raises(ValidationError) as exc_info:
        validate_question_option_limits(question)

    assert exc_info.value.message_dict == {
        "min_options": [
            "Minimum number of options cannot be greater than maximum number of options."
        ]
    }


@pytest.mark.parametrize(
    ("min_options", "max_options"),
    ((1, 3), (2, 2), (None, 2), (3, None), (None, None)),
    ids=("in_order", "equal", "max_only", "min_only", "unset"),
)
def test_validate_question_option_limits_accepts_valid(min_options, max_options):
    question = QuestionFactory.build(min_options=min_options, max_options=max_options)
    validate_question_option_limits(question)


def test_validate_option_count_deduplicates_repeated_options():
    validate_option_count(["7", "7"], None, 1)

    with pytest.raises(ValidationError) as exc_info:
        validate_option_count(["7", "7"], 2, None)

    assert exc_info.value.messages == [
        "Please select at least 2 options. You selected 1 options."
    ]


def test_validate_question_min_options_available_rejects_min_above_option_count():
    question = QuestionFactory(variant=QuestionVariant.MULTIPLE, min_options=3)
    AnswerOptionFactory(question=question)
    AnswerOptionFactory(question=question)

    with pytest.raises(ValidationError) as exc_info:
        validate_question_min_options_available(question)

    assert exc_info.value.message_dict == {
        "min_options": [
            "This custom field only has 2 options, so it cannot require 3 of them."
        ]
    }


@pytest.mark.parametrize(
    ("min_options", "option_count"),
    ((2, 2), (2, 3), (None, 1), (5, 0)),
    ids=("exact", "more_than_needed", "no_minimum", "no_options_yet"),
)
def test_validate_question_min_options_available_accepts_valid(
    min_options, option_count
):
    question = QuestionFactory(
        variant=QuestionVariant.MULTIPLE, min_options=min_options
    )
    for _unused in range(option_count):
        AnswerOptionFactory(question=question)

    validate_question_min_options_available(question)


@pytest.mark.parametrize(
    "variant", (QuestionVariant.CHOICES, QuestionVariant.STRING, QuestionVariant.NUMBER)
)
def test_validate_question_min_options_available_ignores_other_variants(variant):
    question = QuestionFactory(variant=variant, min_options=3)
    AnswerOptionFactory(question=question)

    validate_question_min_options_available(question)
    validate_question_min_options_available(question, option_count=1)


def test_validate_question_min_options_available_skips_unsaved_question():
    question = QuestionFactory.build(variant=QuestionVariant.MULTIPLE, min_options=3)

    validate_question_min_options_available(question)


def test_validate_question_min_options_available_uses_given_option_count():
    question = QuestionFactory(variant=QuestionVariant.MULTIPLE, min_options=3)
    AnswerOptionFactory(question=question)
    AnswerOptionFactory(question=question)

    validate_question_min_options_available(question, option_count=3)


def test_validate_question_min_options_available_rejects_given_option_count():
    question = QuestionFactory(variant=QuestionVariant.MULTIPLE, min_options=3)
    for _unused in range(3):
        AnswerOptionFactory(question=question)

    with pytest.raises(ValidationError) as exc_info:
        validate_question_min_options_available(question, option_count=2)

    assert exc_info.value.message_dict == {
        "min_options": [
            "This custom field only has 2 options, so it cannot require 3 of them."
        ]
    }
