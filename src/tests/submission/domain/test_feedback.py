# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.submission.domain.feedback import create_feedback
from pretalx.submission.models import Feedback
from tests.factories import SpeakerFactory, SubmissionFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_create_feedback_auto_assigns_single_speaker():
    submission = SubmissionFactory()
    speaker = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker)

    feedback = create_feedback(Feedback(talk=submission, review="Wonderful!"))

    assert feedback.pk is not None
    assert feedback.talk == submission
    assert feedback.speaker == speaker
    assert feedback.review == "Wonderful!"


def test_create_feedback_keeps_speaker_none_when_multiple_speakers():
    submission = SubmissionFactory()
    speaker1 = SpeakerFactory(event=submission.event)
    speaker2 = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker1, speaker2)

    feedback = create_feedback(Feedback(talk=submission, review="General feedback"))

    assert feedback.speaker is None


def test_create_feedback_uses_passed_speaker():
    submission = SubmissionFactory()
    speaker1 = SpeakerFactory(event=submission.event)
    speaker2 = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker1, speaker2)

    feedback = create_feedback(
        Feedback(talk=submission, speaker=speaker2, review="Nice!")
    )

    assert feedback.speaker == speaker2


def test_create_feedback_includes_rating():
    submission = SubmissionFactory()
    speaker = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker)

    feedback = create_feedback(Feedback(talk=submission, rating=5, review="Great"))

    assert feedback.rating == 5
