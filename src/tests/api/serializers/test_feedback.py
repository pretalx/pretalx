# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from rest_framework import exceptions

from pretalx.api.serializers.feedback import FeedbackSerializer, FeedbackWriteSerializer
from tests.factories import (
    EventFactory,
    FeedbackFactory,
    SpeakerFactory,
    SpeakerRoleFactory,
    SubmissionFactory,
)
from tests.utils import make_api_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_feedback_write_serializer_init_populates_querysets(published_talk_slot):
    sub = published_talk_slot.submission
    event = sub.event
    speaker = sub.speakers.first()
    serializer = FeedbackWriteSerializer(
        context={"request": make_api_request(event=event)}
    )

    assert list(serializer.fields["submission"].queryset) == [sub]
    assert list(serializer.fields["speaker"].queryset) == [speaker]


def test_feedback_write_serializer_init_without_event_leaves_empty_querysets():
    request = make_api_request()
    serializer = FeedbackWriteSerializer(context={"request": request})

    assert serializer.fields["submission"].queryset.count() == 0
    assert serializer.fields["speaker"].queryset.count() == 0


def test_feedback_write_serializer_validate_submission_rejects_no_feedback():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    serializer = FeedbackWriteSerializer(
        context={"request": make_api_request(event=event)}
    )

    with pytest.raises(exceptions.ValidationError):
        serializer.validate_submission(sub)


def test_feedback_write_serializer_validate_submission_accepts_feedback(
    published_talk_slot,
):
    sub = published_talk_slot.submission
    event = sub.event
    assert sub.does_accept_feedback is True
    serializer = FeedbackWriteSerializer(
        context={"request": make_api_request(event=event)}
    )

    result = serializer.validate_submission(sub)
    assert result == sub


def test_feedback_write_serializer_validate_rejects_unrelated_speaker():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    serializer = FeedbackWriteSerializer(
        context={"request": make_api_request(event=event)}
    )

    with pytest.raises(exceptions.ValidationError, match="speaker"):
        serializer.validate({"talk": sub, "speaker": speaker})


def test_feedback_write_serializer_validate_accepts_related_speaker():
    event = EventFactory()
    role = SpeakerRoleFactory(submission__event=event, speaker__event=event)
    sub = role.submission
    speaker = role.speaker
    serializer = FeedbackWriteSerializer(
        context={"request": make_api_request(event=event)}
    )

    result = serializer.validate({"talk": sub, "speaker": speaker})

    assert result["talk"] == sub
    assert result["speaker"] == speaker


def test_feedback_write_serializer_validate_accepts_no_speaker():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    serializer = FeedbackWriteSerializer(
        context={"request": make_api_request(event=event)}
    )

    result = serializer.validate({"talk": sub})
    assert result["talk"] == sub


def test_feedback_serializer_data():
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
