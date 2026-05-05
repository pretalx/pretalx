# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.submission.enums import (
    QuestionIcon,
    QuestionRequired,
    QuestionTarget,
    QuestionVariant,
    SubmissionStates,
)

pytestmark = pytest.mark.unit


def test_submission_states_get_max_length():
    result = SubmissionStates.get_max_length()
    assert result == max(len(val) for val in SubmissionStates.values)


@pytest.mark.parametrize(
    ("state", "expected_color"),
    (
        ("submitted", "--color-info"),
        ("accepted", "--color-success"),
        ("confirmed", "--color-success"),
        ("rejected", "--color-danger"),
        ("canceled", "--color-grey"),
        ("withdrawn", "--color-grey"),
    ),
    ids=["submitted", "accepted", "confirmed", "rejected", "canceled", "withdrawn"],
)
def test_submission_states_get_color(state, expected_color):
    assert SubmissionStates.get_color(state) == expected_color


def test_submission_states_accepted_states():
    assert SubmissionStates.accepted_states == ("accepted", "confirmed")


def test_question_variant_short_answers():
    assert set(QuestionVariant.short_answers) | set(
        QuestionVariant.long_answers
    ) == set(QuestionVariant.values)
    assert not set(QuestionVariant.short_answers) & set(QuestionVariant.long_answers)


def test_question_variant_long_answers():
    assert QuestionVariant.long_answers == ("text",)


@pytest.mark.parametrize(
    "cls",
    (QuestionVariant, QuestionTarget, QuestionRequired, QuestionIcon),
    ids=("variant", "target", "required", "icon"),
)
def test_question_choices_get_max_length(cls):
    assert cls.get_max_length() == max(len(val) for val in cls.values)
