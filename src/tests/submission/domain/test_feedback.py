# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.submission.domain.feedback import create_feedback
from pretalx.submission.models import Feedback
from tests.factories import SpeakerFactory, SubmissionFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_create_feedback_assigns_speaker_only_when_unambiguous():
    submission = SubmissionFactory()
    speaker1 = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker1)

    feedback = create_feedback(Feedback(talk=submission, rating=5, review="Great"))

    assert feedback.pk is not None
    assert feedback.talk == submission
    assert feedback.speaker == speaker1
    assert feedback.rating == 5
    assert feedback.review == "Great"

    speaker2 = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker2)

    general = create_feedback(Feedback(talk=submission, review="General feedback"))
    assert general.speaker is None

    targeted = create_feedback(
        Feedback(talk=submission, speaker=speaker2, review="Nice!")
    )
    assert targeted.speaker == speaker2
