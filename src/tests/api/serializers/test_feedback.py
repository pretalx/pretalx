# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.serializers.feedback import FeedbackSerializer, FeedbackWriteSerializer
from tests.factories import (
    EventFactory,
    FeedbackFactory,
    SpeakerFactory,
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


def test_feedback_write_serializer_rejects_when_talk_does_not_accept_feedback():
    event = EventFactory()
    sub = SubmissionFactory(event=event)
    serializer = FeedbackWriteSerializer(
        context={"request": make_api_request(event=event)},
        data={"submission": sub.code, "review": "Hi"},
    )

    assert not serializer.is_valid()
    assert "submission" in serializer.errors


def test_feedback_write_serializer_accepts_when_talk_accepts_feedback(
    published_talk_slot,
):
    sub = published_talk_slot.submission
    event = sub.event
    speaker = sub.speakers.first()
    serializer = FeedbackWriteSerializer(
        context={"request": make_api_request(event=event)},
        data={"submission": sub.code, "speaker": speaker.code, "review": "Nice"},
    )

    assert serializer.is_valid(), serializer.errors


def test_feedback_write_serializer_rejects_unrelated_speaker(published_talk_slot):
    sub = published_talk_slot.submission
    event = sub.event
    other_speaker = SpeakerFactory(event=event)
    serializer = FeedbackWriteSerializer(
        context={"request": make_api_request(event=event)},
        data={"submission": sub.code, "speaker": other_speaker.code, "review": "Hi"},
    )

    assert not serializer.is_valid()
    assert "speaker" in serializer.errors


def test_feedback_write_serializer_accepts_related_speaker(published_talk_slot):
    sub = published_talk_slot.submission
    event = sub.event
    speaker = sub.speakers.first()
    serializer = FeedbackWriteSerializer(
        context={"request": make_api_request(event=event)},
        data={"submission": sub.code, "speaker": speaker.code, "review": "Nice"},
    )

    assert serializer.is_valid(), serializer.errors


def test_feedback_write_serializer_accepts_no_speaker(published_talk_slot):
    sub = published_talk_slot.submission
    event = sub.event
    serializer = FeedbackWriteSerializer(
        context={"request": make_api_request(event=event)},
        data={"submission": sub.code, "review": "Nice"},
    )

    assert serializer.is_valid(), serializer.errors


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
