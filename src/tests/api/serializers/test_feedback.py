import pytest
from django_scopes import scopes_disabled
from rest_framework import exceptions

from pretalx.api.serializers.feedback import FeedbackSerializer, FeedbackWriteSerializer
from tests.factories import (
    EventFactory,
    FeedbackFactory,
    SpeakerFactory,
    SubmissionFactory,
)
from tests.utils import make_api_request

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_feedback_write_serializer_init_populates_querysets(published_talk_slot):
    """With a published schedule, querysets contain the event's talks and their speakers."""
    with scopes_disabled():
        sub = published_talk_slot.submission
        event = sub.event
        speaker = sub.speakers.first()
        serializer = FeedbackWriteSerializer(
            context={"request": make_api_request(event=event)}
        )

    assert list(serializer.fields["submission"].queryset) == [sub]
    assert list(serializer.fields["speaker"].queryset) == [speaker]


@pytest.mark.django_db
def test_feedback_write_serializer_init_without_event_leaves_empty_querysets():
    request = make_api_request()
    serializer = FeedbackWriteSerializer(context={"request": request})

    assert serializer.fields["submission"].queryset.count() == 0
    assert serializer.fields["speaker"].queryset.count() == 0


@pytest.mark.django_db
def test_feedback_write_serializer_validate_submission_rejects_no_feedback():
    """Submissions without a published schedule slot don't accept feedback."""
    with scopes_disabled():
        event = EventFactory()
        sub = SubmissionFactory(event=event)
        serializer = FeedbackWriteSerializer(
            context={"request": make_api_request(event=event)}
        )

    with pytest.raises(exceptions.ValidationError):
        serializer.validate_submission(sub)


@pytest.mark.django_db
def test_feedback_write_serializer_validate_submission_accepts_feedback(
    published_talk_slot,
):
    """Submissions with a past slot accept feedback and pass validation."""
    with scopes_disabled():
        sub = published_talk_slot.submission
        event = sub.event
        assert sub.does_accept_feedback is True
        serializer = FeedbackWriteSerializer(
            context={"request": make_api_request(event=event)}
        )

    result = serializer.validate_submission(sub)
    assert result == sub


@pytest.mark.django_db
def test_feedback_write_serializer_validate_rejects_unrelated_speaker():
    """A speaker who is not on the submission is rejected."""
    with scopes_disabled():
        event = EventFactory()
        sub = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        serializer = FeedbackWriteSerializer(
            context={"request": make_api_request(event=event)}
        )

        with pytest.raises(exceptions.ValidationError, match="speaker"):
            serializer.validate({"talk": sub, "speaker": speaker})


@pytest.mark.django_db
def test_feedback_write_serializer_validate_accepts_related_speaker():
    """A speaker who is on the submission passes validation."""
    with scopes_disabled():
        event = EventFactory()
        sub = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        sub.speakers.add(speaker)
        serializer = FeedbackWriteSerializer(
            context={"request": make_api_request(event=event)}
        )

        result = serializer.validate({"talk": sub, "speaker": speaker})

    assert result["talk"] == sub
    assert result["speaker"] == speaker


@pytest.mark.django_db
def test_feedback_write_serializer_validate_accepts_no_speaker():
    """Feedback without a specific speaker passes validation."""
    with scopes_disabled():
        event = EventFactory()
        sub = SubmissionFactory(event=event)
        serializer = FeedbackWriteSerializer(
            context={"request": make_api_request(event=event)}
        )

    result = serializer.validate({"talk": sub})
    assert result["talk"] == sub


@pytest.mark.django_db
def test_feedback_serializer_data():
    """Serialized output includes all fields with slug-based submission and speaker references."""
    with scopes_disabled():
        event = EventFactory()
        sub = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        feedback = FeedbackFactory(talk=sub, speaker=speaker)
        serializer = FeedbackSerializer(
            feedback, context={"request": make_api_request(event=event)}
        )

    assert serializer.data == {
        "id": feedback.id,
        "submission": sub.code,
        "speaker": speaker.code,
        "rating": feedback.rating,
        "review": feedback.review,
    }


@pytest.mark.django_db
def test_feedback_serializer_slug_fields_are_read_only():
    with scopes_disabled():
        event = EventFactory()
        serializer = FeedbackSerializer(
            context={"request": make_api_request(event=event)}
        )

    assert serializer.fields["submission"].read_only is True
    assert serializer.fields["speaker"].read_only is True


def test_feedback_serializer_has_expandable_fields():
    assert set(FeedbackSerializer.Meta.expandable_fields.keys()) == {
        "submission",
        "speaker",
    }
