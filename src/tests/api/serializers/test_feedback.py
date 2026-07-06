# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import datetime as dt

import pytest
from django.utils.timezone import now

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


@pytest.mark.parametrize("hide_via", ("is_public", "show_schedule"))
def test_feedback_write_serializer_hidden_schedule_error_matches_unknown_code(
    published_talk_slot, hide_via
):
    sub = published_talk_slot.submission
    event = sub.event
    if hide_via == "is_public":
        event.is_public = False
    else:
        event.feature_flags["show_schedule"] = False
    event.save()
    request = make_api_request(event=event)

    hidden = FeedbackWriteSerializer(
        context={"request": request}, data={"submission": sub.code, "review": "Hi"}
    )
    unknown = FeedbackWriteSerializer(
        context={"request": request}, data={"submission": "ZZZZZZ", "review": "Hi"}
    )

    assert not hidden.is_valid()
    assert not unknown.is_valid()
    assert hidden.errors["submission"] == [
        f"Object with code={sub.code} does not exist."
    ]
    assert unknown.errors["submission"] == ["Object with code=ZZZZZZ does not exist."]


def test_feedback_write_serializer_rejects_visible_future_session(published_talk_slot):
    sub = published_talk_slot.submission
    event = sub.event
    slot = sub.slots.filter(schedule=event.current_schedule).first()
    slot.start = now() + dt.timedelta(hours=1)
    slot.end = now() + dt.timedelta(hours=2)
    slot.save()

    serializer = FeedbackWriteSerializer(
        context={"request": make_api_request(event=event)},
        data={"submission": sub.code, "review": "Hi"},
    )

    assert not serializer.is_valid()
    assert serializer.errors["submission"] == [
        "This session does not accept feedback yet."
    ]


def test_feedback_write_serializer_ignores_rating(published_talk_slot):
    sub = published_talk_slot.submission
    event = sub.event
    serializer = FeedbackWriteSerializer(
        context={"request": make_api_request(event=event)},
        data={"submission": sub.code, "review": "Nice", "rating": 999},
    )

    assert serializer.is_valid(), serializer.errors
    feedback = serializer.save()
    assert feedback.rating is None


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
    feedback = FeedbackFactory(talk=sub, speaker=speaker, rating=4)
    serializer = FeedbackSerializer(
        feedback, context={"request": make_api_request(event=event)}
    )

    assert serializer.data == {
        "id": feedback.id,
        "submission": sub.code,
        "speaker": speaker.code,
        "review": feedback.review,
    }
