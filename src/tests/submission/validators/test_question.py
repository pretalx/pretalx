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

MIN_ABOVE_COUNT = {
    "min_options": [
        "This custom field only has 2 options, so it cannot require 3 of them."
    ]
}


def _messages(validator, *args, **kwargs):
    try:
        validator(*args, **kwargs)
    except ValidationError as exc:
        return exc.messages
    return []


def _message_dict(validator, *args, **kwargs):
    try:
        validator(*args, **kwargs)
    except ValidationError as exc:
        return exc.message_dict
    return {}


def test_validate_question_identifier_unique_is_case_insensitive_and_skips_self():
    event = EventFactory()
    question = QuestionFactory(event=event, identifier="My-Id")
    error = {
        "identifier": ["This identifier is already used for a different question."]
    }

    assert [
        _message_dict(
            validate_question_identifier_unique, event=event, identifier=identifier
        )
        for identifier in ("Other", "", None, "My-Id", "my-id")
    ] == [{}, {}, {}, error, error]
    assert (
        _message_dict(
            validate_question_identifier_unique,
            event=event,
            identifier="MY-ID",
            instance=question,
        )
        == {}
    )


def test_validate_answer_option_identifier_unique_is_case_insensitive_and_skips_self():
    option = AnswerOptionFactory(identifier="MyOpt")
    question = option.question
    error = {"identifier": ["This identifier is already used for a different option."]}

    assert [
        _message_dict(
            validate_answer_option_identifier_unique,
            question=question,
            identifier=identifier,
        )
        for identifier in ("Other", "", None, "MyOpt", "myopt")
    ] == [{}, {}, {}, error, error]
    assert (
        _message_dict(
            validate_answer_option_identifier_unique,
            question=question,
            identifier="MYOPT",
            instance=option,
        )
        == {}
    )


def test_validate_question_deadline_required_only_after_deadline():
    after_deadline = QuestionFactory.build(
        question_required=QuestionRequired.AFTER_DEADLINE, deadline=None
    )
    optional = QuestionFactory.build(
        question_required=QuestionRequired.OPTIONAL, deadline=None
    )

    assert _message_dict(validate_question_deadline, after_deadline) == {
        "deadline": [
            "Please select a deadline after which the field should become mandatory."
        ]
    }
    assert _message_dict(validate_question_deadline, optional) == {}


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
    ("value", "min_number", "max_number", "messages"),
    (
        (["a", "b"], 1, 5, []),
        (["a", "b", "c"], 3, 3, []),
        ([], None, 5, []),
        (["a"], None, None, []),
        (["7", "7"], None, 1, []),
        (
            ["a"],
            3,
            5,
            ["Please select between 3 and 5 options. You selected 1 options."],
        ),
        (
            ["a", "b", "c", "d"],
            None,
            3,
            ["Please select at most 3 options. You selected 4 options."],
        ),
        (None, 2, None, ["Please select at least 2 options. You selected 0 options."]),
        (
            ["7", "7"],
            2,
            None,
            ["Please select at least 2 options. You selected 1 options."],
        ),
    ),
    ids=(
        "in_range",
        "exact",
        "empty_under_max",
        "no_limits",
        "duplicates_count_once",
        "too_few",
        "too_many",
        "none_below_min",
        "duplicates_too_few",
    ),
)
def test_validate_option_count(value, min_number, max_number, messages):
    assert _messages(validate_option_count, value, min_number, max_number) == messages


@pytest.mark.parametrize(
    ("min_options", "max_options", "errors"),
    (
        (1, 3, {}),
        (2, 2, {}),
        (None, 2, {}),
        (3, None, {}),
        (None, None, {}),
        (
            3,
            2,
            {
                "min_options": [
                    "Minimum number of options cannot be greater than maximum number of options."
                ]
            },
        ),
    ),
    ids=("in_order", "equal", "max_only", "min_only", "unset", "min_above_max"),
)
def test_validate_question_option_limits(min_options, max_options, errors):
    question = QuestionFactory.build(min_options=min_options, max_options=max_options)

    assert _message_dict(validate_question_option_limits, question) == errors


@pytest.mark.parametrize(
    ("min_options", "created_options", "option_count", "errors"),
    (
        (2, 2, None, {}),
        (2, 3, None, {}),
        (None, 1, None, {}),
        (5, 0, None, {}),
        (3, 2, 3, {}),
        (3, 2, None, MIN_ABOVE_COUNT),
        (3, 3, 2, MIN_ABOVE_COUNT),
    ),
    ids=(
        "exact",
        "more_than_needed",
        "no_minimum",
        "no_options_yet",
        "given_count_wins",
        "min_above_count",
        "min_above_given_count",
    ),
)
def test_validate_question_min_options_available(
    min_options, created_options, option_count, errors
):
    question = QuestionFactory(
        variant=QuestionVariant.MULTIPLE, min_options=min_options
    )
    for _unused in range(created_options):
        AnswerOptionFactory(question=question)

    assert (
        _message_dict(
            validate_question_min_options_available, question, option_count=option_count
        )
        == errors
    )


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
