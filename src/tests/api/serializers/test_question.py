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


def test_question_orga_serializer_create_sets_event():
    event = EventFactory()
    request = make_api_request(event=event)
    serializer = QuestionOrgaSerializer(
        data={
            "question": "Test question",
            "variant": QuestionVariant.STRING,
            "target": QuestionTarget.SUBMISSION,
        },
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    question = serializer.save()

    assert question.event == event
    assert question.question == "Test question"


def test_question_orga_serializer_create_with_options():
    event = EventFactory()
    request = make_api_request(event=event)
    serializer = QuestionOrgaSerializer(
        data={
            "question": "Choice question",
            "variant": QuestionVariant.CHOICES,
            "target": QuestionTarget.SUBMISSION,
            "options": [{"answer": "Option A"}, {"answer": "Option B"}],
        },
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    question = serializer.save()
    options = sorted(str(a) for a in question.options.values_list("answer", flat=True))

    assert options == ["Option A", "Option B"]


def test_question_orga_serializer_update_replaces_options():
    event = EventFactory()
    question = QuestionFactory(event=event, variant=QuestionVariant.CHOICES)
    AnswerOptionFactory(question=question, answer="Old option")

    request = make_api_request(event=event)
    serializer = QuestionOrgaSerializer(
        instance=question,
        data={"options": [{"answer": "New option"}]},
        partial=True,
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()
    options = list(updated.options.values_list("answer", flat=True))

    assert options == ["New option"]


def test_question_orga_serializer_update_without_options_preserves_existing():
    event = EventFactory()
    question = QuestionFactory(event=event, variant=QuestionVariant.CHOICES)
    AnswerOptionFactory(question=question, answer="Existing option")

    request = make_api_request(event=event)
    serializer = QuestionOrgaSerializer(
        instance=question,
        data={"question": "Updated question text"},
        partial=True,
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()
    options = list(updated.options.values_list("answer", flat=True))

    assert updated.question == "Updated question text"
    assert options == ["Existing option"]


def test_answer_serializer_validate_rejects_option_count_outside_limits():
    question = QuestionFactory(
        target=QuestionTarget.SUBMISSION,
        variant=QuestionVariant.MULTIPLE,
        min_options=1,
        max_options=1,
    )
    options = [AnswerOptionFactory(question=question) for _ in range(2)]
    submission = SubmissionFactory(event=question.event)
    answer = AnswerFactory(question=question, submission=submission)
    answer.options.set(options[:1])

    serializer = AnswerSerializer(
        instance=answer,
        data={"options": [option.pk for option in options]},
        partial=True,
    )

    assert not serializer.is_valid()
    assert [str(error) for error in serializer.errors["options"]] == [
        "Please select exactly 1 options. You selected 2 options."
    ]


def test_question_orga_serializer_rejects_min_options_above_max_options():
    event = EventFactory()
    request = make_api_request(event=event)
    serializer = QuestionOrgaSerializer(
        data={
            "question": "Pick some",
            "variant": QuestionVariant.MULTIPLE,
            "target": QuestionTarget.SUBMISSION,
            "min_options": 3,
            "max_options": 2,
        },
        context={"request": request},
    )

    assert not serializer.is_valid()
    assert [str(error) for error in serializer.errors["min_options"]] == [
        "Minimum number of options cannot be greater than maximum number of options."
    ]


def test_answer_serializer_validate_counts_repeated_options_only_once():
    question = QuestionFactory(
        target=QuestionTarget.SUBMISSION,
        variant=QuestionVariant.MULTIPLE,
        min_options=2,
    )
    option = AnswerOptionFactory(question=question)
    AnswerOptionFactory(question=question)
    submission = SubmissionFactory(event=question.event)
    answer = AnswerFactory(question=question, submission=submission)

    serializer = AnswerSerializer(
        instance=answer, data={"options": [option.pk, option.pk]}, partial=True
    )

    assert not serializer.is_valid()
    assert [str(error) for error in serializer.errors["options"]] == [
        "Please select at least 2 options. You selected 1 options."
    ]


@pytest.mark.parametrize("field", ("min_options", "max_options"))
def test_question_orga_serializer_rejects_zero_option_limits(field):
    event = EventFactory()
    request = make_api_request(event=event)
    serializer = QuestionOrgaSerializer(
        data={
            "question": "Pick some",
            "variant": QuestionVariant.MULTIPLE,
            "target": QuestionTarget.SUBMISSION,
            field: 0,
        },
        context={"request": request},
    )

    assert not serializer.is_valid()
    assert [str(error) for error in serializer.errors[field]] == [
        "Ensure this value is greater than or equal to 1."
    ]


def test_question_orga_serializer_rejects_min_options_above_option_count():
    event = EventFactory()
    question = QuestionFactory(
        event=event, variant=QuestionVariant.MULTIPLE, target=QuestionTarget.SUBMISSION
    )
    AnswerOptionFactory(question=question)
    AnswerOptionFactory(question=question)
    request = make_api_request(event=event)

    serializer = QuestionOrgaSerializer(
        instance=question,
        data={"min_options": 3},
        partial=True,
        context={"request": request},
    )

    assert not serializer.is_valid()
    assert [str(error) for error in serializer.errors["min_options"]] == [
        "This custom field only has 2 options, so it cannot require 3 of them."
    ]


def test_question_orga_serializer_accepts_min_options_matching_new_options():
    event = EventFactory()
    question = QuestionFactory(
        event=event, variant=QuestionVariant.MULTIPLE, target=QuestionTarget.SUBMISSION
    )
    AnswerOptionFactory(question=question)
    AnswerOptionFactory(question=question)
    request = make_api_request(event=event)

    serializer = QuestionOrgaSerializer(
        instance=question,
        data={
            "min_options": 4,
            "options": [{"answer": f"Option {index}"} for index in range(4)],
        },
        partial=True,
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    question = serializer.save()

    assert question.min_options == 4
    assert question.options.count() == 4


def test_question_orga_serializer_rejects_create_with_too_few_options():
    event = EventFactory()
    request = make_api_request(event=event)

    serializer = QuestionOrgaSerializer(
        data={
            "question": "Pick some",
            "variant": QuestionVariant.MULTIPLE,
            "target": QuestionTarget.SUBMISSION,
            "min_options": 3,
            "options": [{"answer": "First"}, {"answer": "Second"}],
        },
        context={"request": request},
    )

    assert not serializer.is_valid()
    assert [str(error) for error in serializer.errors["min_options"]] == [
        "This custom field only has 2 options, so it cannot require 3 of them."
    ]


def test_question_orga_serializer_ignores_min_options_for_other_variants():
    event = EventFactory()
    question = QuestionFactory(
        event=event,
        variant=QuestionVariant.MULTIPLE,
        target=QuestionTarget.SUBMISSION,
        min_options=3,
    )
    AnswerOptionFactory(question=question)
    AnswerOptionFactory(question=question)
    request = make_api_request(event=event)

    serializer = QuestionOrgaSerializer(
        instance=question,
        data={"variant": QuestionVariant.CHOICES},
        partial=True,
        context={"request": request},
    )
    assert serializer.is_valid(), serializer.errors
    question = serializer.save()

    assert question.variant == QuestionVariant.CHOICES


def test_question_orga_serializer_accepts_min_options_on_question_without_options():
    event = EventFactory()
    request = make_api_request(event=event)
    serializer = QuestionOrgaSerializer(
        data={
            "question": "Pick some",
            "variant": QuestionVariant.MULTIPLE,
            "target": QuestionTarget.SUBMISSION,
            "min_options": 2,
        },
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors
    question = serializer.save(event=event)

    assert question.min_options == 2


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

    assert "options" in exc_info.value.detail


def test_answer_create_serializer_validate_options_must_match_question():
    question = QuestionFactory(variant=QuestionVariant.CHOICES)
    other_question = QuestionFactory()
    wrong_option = AnswerOptionFactory(question=other_question)

    serializer = AnswerCreateSerializer()
    serializer.instance = None

    with pytest.raises(exceptions.ValidationError) as exc_info:
        serializer.validate({"question": question, "options": [wrong_option]})

    assert "options" in exc_info.value.detail


@pytest.mark.parametrize(
    ("target", "error_field"),
    (
        (QuestionTarget.SUBMISSION, "submission"),
        (QuestionTarget.REVIEWER, "review"),
        (QuestionTarget.SPEAKER, "person"),
    ),
)
def test_answer_create_serializer_validate_requires_target_field(target, error_field):
    question = QuestionFactory(target=target)

    serializer = AnswerCreateSerializer()
    serializer.instance = None

    with pytest.raises(exceptions.ValidationError) as exc_info:
        serializer.validate({"question": question})

    assert error_field in exc_info.value.detail


def test_answer_create_serializer_validate_rejects_review_on_submission_question():
    question = QuestionFactory(target=QuestionTarget.SUBMISSION)
    submission = SubmissionFactory(event=question.event)
    review = ReviewFactory(submission=submission)

    serializer = AnswerCreateSerializer()
    serializer.instance = None

    with pytest.raises(exceptions.ValidationError) as exc_info:
        serializer.validate(
            {"question": question, "submission": submission, "review": review}
        )

    assert "review" in exc_info.value.detail


def test_answer_create_serializer_validate_rejects_submission_on_reviewer_question():
    question = QuestionFactory(target=QuestionTarget.REVIEWER)
    submission = SubmissionFactory(event=question.event)
    review = ReviewFactory(submission=submission)

    serializer = AnswerCreateSerializer()
    serializer.instance = None

    with pytest.raises(exceptions.ValidationError) as exc_info:
        serializer.validate(
            {"question": question, "review": review, "submission": submission}
        )

    assert "submission" in exc_info.value.detail


def test_answer_create_serializer_validate_rejects_submission_on_speaker_question():
    question = QuestionFactory(target=QuestionTarget.SPEAKER)
    speaker = SpeakerFactory(event=question.event)
    submission = SubmissionFactory(event=question.event)

    serializer = AnswerCreateSerializer()
    serializer.instance = None

    with pytest.raises(exceptions.ValidationError) as exc_info:
        serializer.validate(
            {"question": question, "speaker": speaker, "submission": submission}
        )

    assert "submission" in exc_info.value.detail


def test_answer_create_serializer_validate_accepts_valid_submission_answer():
    question = QuestionFactory(
        target=QuestionTarget.SUBMISSION, variant=QuestionVariant.STRING
    )
    submission = SubmissionFactory(event=question.event)

    serializer = AnswerCreateSerializer()
    serializer.instance = None

    result = serializer.validate({"question": question, "submission": submission})

    assert result["question"] == question
    assert result["submission"] == submission


def test_answer_create_serializer_validate_accepts_valid_speaker_answer():
    question = QuestionFactory(
        target=QuestionTarget.SPEAKER, variant=QuestionVariant.STRING
    )
    speaker = SpeakerFactory(event=question.event)

    serializer = AnswerCreateSerializer()
    serializer.instance = None

    result = serializer.validate({"question": question, "speaker": speaker})

    assert result["question"] == question
    assert result["speaker"] == speaker


def test_answer_create_serializer_validate_accepts_valid_choice_answer():
    question = QuestionFactory(
        target=QuestionTarget.SUBMISSION, variant=QuestionVariant.CHOICES
    )
    option = AnswerOptionFactory(question=question)
    submission = SubmissionFactory(event=question.event)

    serializer = AnswerCreateSerializer()
    serializer.instance = None

    result = serializer.validate(
        {"question": question, "submission": submission, "options": [option]}
    )

    assert result["options"] == [option]


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


def test_answer_create_serializer_validate_accepts_option_count_within_limits():
    question = QuestionFactory(
        target=QuestionTarget.SUBMISSION,
        variant=QuestionVariant.MULTIPLE,
        min_options=1,
        max_options=2,
    )
    options = [AnswerOptionFactory(question=question) for _ in range(2)]
    submission = SubmissionFactory(event=question.event)

    serializer = AnswerCreateSerializer()
    serializer.instance = None

    result = serializer.validate(
        {"question": question, "submission": submission, "options": options}
    )

    assert result["options"] == options
