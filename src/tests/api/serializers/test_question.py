# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from rest_framework import exceptions

from pretalx.api.serializers.question import (
    AnswerCreateSerializer,
    AnswerOptionCreateSerializer,
    AnswerOptionSerializer,
    AnswerSerializer,
    QuestionOrgaSerializer,
    QuestionSerializer,
)
from pretalx.submission.models import (
    Question,
    QuestionTarget,
    QuestionVariant,
    SubmissionType,
    Track,
)
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
from tests.utils import make_api_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_answer_option_serializer_data():
    option = AnswerOptionFactory()
    data = AnswerOptionSerializer(option).data

    assert set(data.keys()) == {"id", "question", "answer", "position", "identifier"}
    assert data["id"] == option.id
    assert data["question"] == option.question_id
    assert data["answer"] == {"en": str(option.answer)}
    assert data["position"] == option.position
    assert data["identifier"] == option.identifier


def test_answer_option_create_serializer_init_filters_question_queryset():
    event = EventFactory()
    choice_q = QuestionFactory(
        event=event, variant=QuestionVariant.CHOICES, target=QuestionTarget.SUBMISSION
    )
    multiple_q = QuestionFactory(
        event=event, variant=QuestionVariant.MULTIPLE, target=QuestionTarget.SUBMISSION
    )
    QuestionFactory(
        event=event, variant=QuestionVariant.STRING, target=QuestionTarget.SUBMISSION
    )

    request = make_api_request(event=event)
    serializer = AnswerOptionCreateSerializer(context={"request": request})

    queryset = serializer.fields["question"].queryset
    assert set(queryset) == {choice_q, multiple_q}


def test_answer_option_create_serializer_init_without_request():
    serializer = AnswerOptionCreateSerializer()

    queryset = serializer.fields["question"].queryset
    assert queryset.model is Question
    assert queryset.count() == 0


def test_question_serializer_data():
    question = QuestionFactory(
        variant=QuestionVariant.STRING, target=QuestionTarget.SUBMISSION
    )
    data = QuestionSerializer(question).data

    assert set(data.keys()) == {
        "id",
        "identifier",
        "question",
        "help_text",
        "default_answer",
        "variant",
        "target",
        "deadline",
        "freeze_after",
        "question_required",
        "position",
        "tracks",
        "submission_types",
        "options",
        "min_length",
        "max_length",
        "min_number",
        "max_number",
        "min_date",
        "max_date",
        "min_datetime",
        "max_datetime",
        "min_options",
        "max_options",
        "icon",
    }
    assert data["id"] == question.id
    assert data["variant"] == QuestionVariant.STRING
    assert data["target"] == QuestionTarget.SUBMISSION
    assert data["identifier"] == question.identifier


def test_question_orga_serializer_fields():
    question = QuestionFactory()
    base_data = QuestionSerializer(question).data
    orga_data = QuestionOrgaSerializer(question).data

    assert set(orga_data.keys()) - set(base_data.keys()) == {
        "active",
        "is_public",
        "contains_personal_data",
        "is_visible_to_reviewers",
    }


def test_question_orga_serializer_init_sets_querysets():
    event = EventFactory()
    default_type = event.submission_types.first()
    sub_type = SubmissionTypeFactory(event=event)
    SubmissionTypeFactory()
    track = TrackFactory(event=event)
    TrackFactory()

    request = make_api_request(event=event)
    serializer = QuestionOrgaSerializer(context={"request": request})

    assert list(serializer.fields["tracks"].child_relation.queryset) == [track]
    assert set(serializer.fields["submission_types"].child_relation.queryset) == {
        default_type,
        sub_type,
    }


def test_question_orga_serializer_init_without_request_sets_empty_querysets():
    serializer = QuestionOrgaSerializer()

    assert serializer.fields["tracks"].child_relation.queryset.model is Track
    assert serializer.fields["tracks"].child_relation.queryset.count() == 0
    assert (
        serializer.fields["submission_types"].child_relation.queryset.model
        is SubmissionType
    )
    assert serializer.fields["submission_types"].child_relation.queryset.count() == 0


@pytest.mark.parametrize(
    ("options", "expected_options"),
    (
        (None, []),
        ([{"answer": "Option A"}, {"answer": "Option B"}], ["Option A", "Option B"]),
    ),
    ids=("without_options", "with_options"),
)
def test_question_orga_serializer_create_sets_event_and_options(
    options, expected_options
):
    event = EventFactory()
    request = make_api_request(event=event)
    data = {
        "question": "Test question",
        "variant": QuestionVariant.CHOICES,
        "target": QuestionTarget.SUBMISSION,
    }
    if options is not None:
        data["options"] = options
    serializer = QuestionOrgaSerializer(data=data, context={"request": request})
    assert serializer.is_valid(), serializer.errors
    question = serializer.save()

    assert question.event == event
    assert question.question == "Test question"
    assert (
        sorted(str(a) for a in question.options.values_list("answer", flat=True))
        == expected_options
    )


@pytest.mark.parametrize(
    ("data", "expected_question", "expected_options"),
    (
        ({"options": [{"answer": "New option"}]}, "Old question", ["New option"]),
        (
            {"question": "Updated question text"},
            "Updated question text",
            ["Old option"],
        ),
    ),
    ids=("replaces_options", "preserves_options_when_absent"),
)
def test_question_orga_serializer_update_options(
    data, expected_question, expected_options
):
    event = EventFactory()
    question = QuestionFactory(
        event=event, variant=QuestionVariant.CHOICES, question="Old question"
    )
    AnswerOptionFactory(question=question, answer="Old option")

    request = make_api_request(event=event)
    serializer = QuestionOrgaSerializer(
        instance=question, data=data, partial=True, context={"request": request}
    )
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()

    assert updated.question == expected_question
    assert list(updated.options.values_list("answer", flat=True)) == expected_options


@pytest.mark.parametrize(
    ("min_options", "max_options", "picks", "error"),
    (
        (1, 1, (0, 1), "Please select exactly 1 options. You selected 2 options."),
        (2, None, (0, 0), "Please select at least 2 options. You selected 1 options."),
    ),
    ids=("outside_limits", "repeated_option_counts_once"),
)
def test_answer_serializer_validate_rejects_option_count(
    min_options, max_options, picks, error
):
    question = QuestionFactory(
        target=QuestionTarget.SUBMISSION,
        variant=QuestionVariant.MULTIPLE,
        min_options=min_options,
        max_options=max_options,
    )
    options = [AnswerOptionFactory(question=question) for _ in range(2)]
    submission = SubmissionFactory(event=question.event)
    answer = AnswerFactory(question=question, submission=submission)

    serializer = AnswerSerializer(
        instance=answer,
        data={"options": [options[index].pk for index in picks]},
        partial=True,
    )

    assert not serializer.is_valid()
    assert serializer.errors == {"options": [error]}


@pytest.mark.parametrize(
    ("data", "errors"),
    (
        (
            {"min_options": 3, "max_options": 2},
            {
                "min_options": [
                    "Minimum number of options cannot be greater than maximum number of options."
                ]
            },
        ),
        (
            {"min_options": 0},
            {"min_options": ["Ensure this value is greater than or equal to 1."]},
        ),
        (
            {"max_options": 0},
            {"max_options": ["Ensure this value is greater than or equal to 1."]},
        ),
        (
            {"min_options": 3, "options": [{"answer": "First"}, {"answer": "Second"}]},
            {
                "min_options": [
                    "This custom field only has 2 options, so it cannot require 3 of them."
                ]
            },
        ),
        ({"min_options": 2}, {}),
    ),
    ids=(
        "min_above_max",
        "zero_min",
        "zero_max",
        "min_above_option_count",
        "min_without_options",
    ),
)
def test_question_orga_serializer_create_validates_option_limits(data, errors):
    event = EventFactory()
    request = make_api_request(event=event)
    serializer = QuestionOrgaSerializer(
        data={
            "question": "Pick some",
            "variant": QuestionVariant.MULTIPLE,
            "target": QuestionTarget.SUBMISSION,
            **data,
        },
        context={"request": request},
    )

    assert serializer.is_valid() == (not errors)
    assert serializer.errors == errors


@pytest.mark.parametrize(
    ("data", "errors"),
    (
        (
            {"min_options": 3},
            {
                "min_options": [
                    "This custom field only has 2 options, so it cannot require 3 of them."
                ]
            },
        ),
        (
            {
                "min_options": 4,
                "options": [{"answer": f"Option {index}"} for index in range(4)],
            },
            {},
        ),
        ({"min_options": 3, "variant": QuestionVariant.CHOICES}, {}),
    ),
    ids=("above_option_count", "matching_new_options", "ignored_for_other_variant"),
)
def test_question_orga_serializer_update_validates_min_options(data, errors):
    event = EventFactory()
    question = QuestionFactory(
        event=event, variant=QuestionVariant.MULTIPLE, target=QuestionTarget.SUBMISSION
    )
    AnswerOptionFactory(question=question)
    AnswerOptionFactory(question=question)
    request = make_api_request(event=event)

    serializer = QuestionOrgaSerializer(
        instance=question, data=data, partial=True, context={"request": request}
    )

    assert serializer.is_valid() == (not errors)
    assert serializer.errors == errors


def test_answer_serializer_data():
    answer = AnswerFactory()
    data = AnswerSerializer(answer).data

    assert data == {
        "id": answer.id,
        "question": answer.question_id,
        "answer": answer.answer,
        "answer_file": None,
        "submission": answer.submission.code,
        "review": None,
        "person": None,
        "options": [],
    }


def test_answer_create_serializer_init_sets_querysets(user_with_event):
    user, event = user_with_event
    question = QuestionFactory(event=event)
    QuestionFactory()

    request = make_api_request(event=event, user=user)
    serializer = AnswerCreateSerializer(context={"request": request})

    assert set(serializer.fields["question"].queryset) == {question}


def test_answer_create_serializer_init_without_request():
    serializer = AnswerCreateSerializer(context={})
    QuestionFactory()

    assert serializer.fields["question"].queryset.count() == 0


@pytest.mark.parametrize("variant", (QuestionVariant.CHOICES, QuestionVariant.MULTIPLE))
def test_answer_create_serializer_validate_requires_options_for_choice_variant(variant):
    question = QuestionFactory(variant=variant)

    serializer = AnswerCreateSerializer()
    serializer.instance = None

    with pytest.raises(exceptions.ValidationError) as exc_info:
        serializer.validate({"question": question, "options": []})

    assert exc_info.value.detail == {
        "options": "This field is required for choice or multiple-choice question."
    }


def test_answer_create_serializer_validate_options_must_match_question():
    question = QuestionFactory(variant=QuestionVariant.CHOICES)
    other_question = QuestionFactory()
    wrong_option = AnswerOptionFactory(question=other_question)

    serializer = AnswerCreateSerializer()
    serializer.instance = None

    with pytest.raises(exceptions.ValidationError) as exc_info:
        serializer.validate({"question": question, "options": [wrong_option]})

    assert exc_info.value.detail == {
        "options": f"Option {wrong_option.pk} does not belong to question {question.pk}."
    }


@pytest.mark.parametrize(
    ("target", "fields", "errors"),
    (
        (
            QuestionTarget.SUBMISSION,
            (),
            {"submission": "This field is required for submission questions."},
        ),
        (
            QuestionTarget.REVIEWER,
            (),
            {"review": "This field is required for reviewer questions."},
        ),
        (
            QuestionTarget.SPEAKER,
            (),
            {"person": "This field is required for speaker questions."},
        ),
        (
            QuestionTarget.SUBMISSION,
            ("submission", "review"),
            {"review": "Cannot set review for submission question."},
        ),
        (
            QuestionTarget.REVIEWER,
            ("review", "submission"),
            {"submission": "Cannot set submission for reviewer question."},
        ),
        (
            QuestionTarget.SPEAKER,
            ("speaker", "submission"),
            {"submission": "Cannot set submission for speaker question."},
        ),
    ),
)
def test_answer_create_serializer_validate_requires_exactly_the_target_field(
    target, fields, errors
):
    question = QuestionFactory(target=target)
    submission = SubmissionFactory(event=question.event)
    objects = {
        "submission": submission,
        "review": ReviewFactory(submission=submission),
        "speaker": SpeakerFactory(event=question.event),
    }

    serializer = AnswerCreateSerializer()
    serializer.instance = None

    with pytest.raises(exceptions.ValidationError) as exc_info:
        serializer.validate(
            {"question": question, **{field: objects[field] for field in fields}}
        )

    assert exc_info.value.detail == errors


@pytest.mark.parametrize(
    ("target", "field", "factory"),
    (
        (QuestionTarget.SUBMISSION, "submission", SubmissionFactory),
        (QuestionTarget.SPEAKER, "speaker", SpeakerFactory),
    ),
)
def test_answer_create_serializer_validate_accepts_target_field(target, field, factory):
    question = QuestionFactory(target=target, variant=QuestionVariant.STRING)
    data = {"question": question, field: factory(event=question.event)}

    serializer = AnswerCreateSerializer()
    serializer.instance = None

    assert serializer.validate(data) == data


@pytest.mark.parametrize(
    ("variant", "min_options", "max_options", "selected"),
    ((QuestionVariant.CHOICES, None, None, 1), (QuestionVariant.MULTIPLE, 1, 2, 2)),
)
def test_answer_create_serializer_validate_accepts_options_within_limits(
    variant, min_options, max_options, selected
):
    question = QuestionFactory(
        target=QuestionTarget.SUBMISSION,
        variant=variant,
        min_options=min_options,
        max_options=max_options,
    )
    options = [AnswerOptionFactory(question=question) for _ in range(selected)]
    submission = SubmissionFactory(event=question.event)

    serializer = AnswerCreateSerializer()
    serializer.instance = None

    result = serializer.validate(
        {"question": question, "submission": submission, "options": options}
    )

    assert result["options"] == options


@pytest.mark.parametrize(
    ("min_options", "max_options", "selected"),
    ((2, None, 1), (None, 1, 2)),
    ids=("too_few", "too_many"),
)
def test_answer_create_serializer_validate_rejects_option_count_outside_limits(
    min_options, max_options, selected
):
    question = QuestionFactory(
        target=QuestionTarget.SUBMISSION,
        variant=QuestionVariant.MULTIPLE,
        min_options=min_options,
        max_options=max_options,
    )
    options = [AnswerOptionFactory(question=question) for _ in range(2)]
    submission = SubmissionFactory(event=question.event)

    serializer = AnswerCreateSerializer()
    serializer.instance = None

    with pytest.raises(exceptions.ValidationError) as exc_info:
        serializer.validate(
            {
                "question": question,
                "submission": submission,
                "options": options[:selected],
            }
        )

    assert "options" in exc_info.value.detail
