import pytest
from django_scopes import scopes_disabled
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

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_answer_option_serializer_data():
    with scopes_disabled():
        option = AnswerOptionFactory()
        data = AnswerOptionSerializer(option).data

    assert set(data.keys()) == {"id", "question", "answer", "position", "identifier"}
    assert data["id"] == option.id
    assert data["question"] == option.question_id
    assert data["answer"] == {"en": str(option.answer)}
    assert data["position"] == option.position
    assert data["identifier"] == option.identifier


@pytest.mark.django_db
def test_answer_option_create_serializer_init_filters_question_queryset():
    """Only questions with choices or multiple variant are available."""
    with scopes_disabled():
        event = EventFactory()
        choice_q = QuestionFactory(
            event=event,
            variant=QuestionVariant.CHOICES,
            target=QuestionTarget.SUBMISSION,
        )
        multiple_q = QuestionFactory(
            event=event,
            variant=QuestionVariant.MULTIPLE,
            target=QuestionTarget.SUBMISSION,
        )
        QuestionFactory(
            event=event,
            variant=QuestionVariant.STRING,
            target=QuestionTarget.SUBMISSION,
        )

        request = make_api_request(event=event)
        serializer = AnswerOptionCreateSerializer(context={"request": request})

        queryset = serializer.fields["question"].queryset
        assert set(queryset) == {choice_q, multiple_q}


@pytest.mark.django_db
def test_answer_option_create_serializer_init_without_request():
    serializer = AnswerOptionCreateSerializer()

    queryset = serializer.fields["question"].queryset
    assert queryset.model is Question
    assert queryset.count() == 0


def test_answer_option_create_serializer_validators_empty():
    serializer = AnswerOptionCreateSerializer()

    assert serializer.Meta.validators == []


@pytest.mark.django_db
def test_question_serializer_fields():
    with scopes_disabled():
        question = QuestionFactory()
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
        "icon",
    }


@pytest.mark.django_db
def test_question_serializer_data():
    with scopes_disabled():
        question = QuestionFactory(
            variant=QuestionVariant.STRING, target=QuestionTarget.SUBMISSION
        )
        data = QuestionSerializer(question).data

    assert data["id"] == question.id
    assert data["variant"] == QuestionVariant.STRING
    assert data["target"] == QuestionTarget.SUBMISSION
    assert data["identifier"] == question.identifier


@pytest.mark.django_db
def test_question_orga_serializer_fields():
    """QuestionOrgaSerializer includes additional organiser-only fields."""
    with scopes_disabled():
        question = QuestionFactory()
        base_data = QuestionSerializer(question).data
        orga_data = QuestionOrgaSerializer(question).data

    assert set(orga_data.keys()) - set(base_data.keys()) == {
        "active",
        "is_public",
        "contains_personal_data",
        "is_visible_to_reviewers",
    }


@pytest.mark.django_db
def test_question_orga_serializer_init_sets_track_queryset():
    with scopes_disabled():
        event = EventFactory()
        track = TrackFactory(event=event)
        TrackFactory()

        request = make_api_request(event=event)
        serializer = QuestionOrgaSerializer(context={"request": request})

        assert list(serializer.fields["tracks"].queryset) == [track]


@pytest.mark.django_db
def test_question_orga_serializer_init_sets_submission_type_queryset():
    """Queryset includes event types (including auto-created default) but not other events'."""
    with scopes_disabled():
        event = EventFactory()
        default_type = event.submission_types.first()
        sub_type = SubmissionTypeFactory(event=event)
        SubmissionTypeFactory()

        request = make_api_request(event=event)
        serializer = QuestionOrgaSerializer(context={"request": request})

        assert set(serializer.fields["submission_types"].queryset) == {
            default_type,
            sub_type,
        }


@pytest.mark.django_db
def test_question_orga_serializer_init_without_request_sets_empty_querysets():
    serializer = QuestionOrgaSerializer()

    assert serializer.fields["tracks"].queryset.model is Track
    assert serializer.fields["tracks"].queryset.count() == 0
    assert serializer.fields["submission_types"].queryset.model is SubmissionType
    assert serializer.fields["submission_types"].queryset.count() == 0


@pytest.mark.django_db
def test_question_orga_serializer_create_sets_event():
    with scopes_disabled():
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


@pytest.mark.django_db
def test_question_orga_serializer_create_with_options():
    with scopes_disabled():
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
        options = sorted(
            str(a) for a in question.options.values_list("answer", flat=True)
        )

    assert options == ["Option A", "Option B"]


@pytest.mark.django_db
def test_question_orga_serializer_update_replaces_options():
    with scopes_disabled():
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


@pytest.mark.django_db
def test_question_orga_serializer_update_without_options_preserves_existing():
    with scopes_disabled():
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


@pytest.mark.django_db
def test_answer_serializer_data():
    with scopes_disabled():
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


@pytest.mark.django_db
def test_answer_create_serializer_init_sets_querysets(user_with_event):
    """Orga user gets question queryset scoped to their event."""
    user, event = user_with_event
    with scopes_disabled():
        question = QuestionFactory(event=event)
        QuestionFactory()

        request = make_api_request(event=event, user=user)
        serializer = AnswerCreateSerializer(context={"request": request})

        assert set(serializer.fields["question"].queryset) == {question}


@pytest.mark.django_db
def test_answer_create_serializer_init_without_request():
    serializer = AnswerCreateSerializer(context={})

    assert serializer.fields["question"].queryset.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("variant", (QuestionVariant.CHOICES, QuestionVariant.MULTIPLE))
def test_answer_create_serializer_validate_requires_options_for_choice_variant(variant):
    with scopes_disabled():
        question = QuestionFactory(variant=variant)

    serializer = AnswerCreateSerializer()
    serializer.instance = None

    with pytest.raises(exceptions.ValidationError) as exc_info:
        serializer.validate({"question": question, "options": []})

    assert "options" in exc_info.value.detail


@pytest.mark.django_db
def test_answer_create_serializer_validate_options_must_match_question():
    with scopes_disabled():
        question = QuestionFactory(variant=QuestionVariant.CHOICES)
        other_question = QuestionFactory()
        wrong_option = AnswerOptionFactory(question=other_question)

    serializer = AnswerCreateSerializer()
    serializer.instance = None

    with pytest.raises(exceptions.ValidationError) as exc_info:
        serializer.validate({"question": question, "options": [wrong_option]})

    assert "options" in exc_info.value.detail


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("target", "error_field"),
    (
        (QuestionTarget.SUBMISSION, "submission"),
        (QuestionTarget.REVIEWER, "review"),
        (QuestionTarget.SPEAKER, "person"),
    ),
)
def test_answer_create_serializer_validate_requires_target_field(target, error_field):
    with scopes_disabled():
        question = QuestionFactory(target=target)

    serializer = AnswerCreateSerializer()
    serializer.instance = None

    with pytest.raises(exceptions.ValidationError) as exc_info:
        serializer.validate({"question": question})

    assert error_field in exc_info.value.detail


@pytest.mark.django_db
def test_answer_create_serializer_validate_rejects_review_on_submission_question():
    with scopes_disabled():
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


@pytest.mark.django_db
def test_answer_create_serializer_validate_rejects_submission_on_reviewer_question():
    with scopes_disabled():
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


@pytest.mark.django_db
def test_answer_create_serializer_validate_rejects_submission_on_speaker_question():
    with scopes_disabled():
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


@pytest.mark.django_db
def test_answer_create_serializer_validate_accepts_valid_submission_answer():
    with scopes_disabled():
        question = QuestionFactory(
            target=QuestionTarget.SUBMISSION, variant=QuestionVariant.STRING
        )
        submission = SubmissionFactory(event=question.event)

    serializer = AnswerCreateSerializer()
    serializer.instance = None

    result = serializer.validate({"question": question, "submission": submission})

    assert result["question"] == question
    assert result["submission"] == submission


@pytest.mark.django_db
def test_answer_create_serializer_validate_accepts_valid_speaker_answer():
    with scopes_disabled():
        question = QuestionFactory(
            target=QuestionTarget.SPEAKER, variant=QuestionVariant.STRING
        )
        speaker = SpeakerFactory(event=question.event)

    serializer = AnswerCreateSerializer()
    serializer.instance = None

    result = serializer.validate({"question": question, "speaker": speaker})

    assert result["question"] == question
    assert result["speaker"] == speaker


@pytest.mark.django_db
def test_answer_create_serializer_validate_accepts_valid_choice_answer():
    with scopes_disabled():
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
