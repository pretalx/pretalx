# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scope

from pretalx.submission.domain.queries.feedback import feedback_for_speaker
from tests.factories import (
    FeedbackFactory,
    SpeakerFactory,
    SubmissionFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_feedback_for_speaker_returns_own_and_general(event):
    talk = SubmissionFactory(event=event)
    speaker_a = SpeakerFactory(event=event)
    speaker_b = SpeakerFactory(event=event)
    talk.speakers.add(speaker_a, speaker_b)

    own = FeedbackFactory(talk=talk, speaker=speaker_a)
    general = FeedbackFactory(talk=talk, speaker=None)
    FeedbackFactory(talk=talk, speaker=speaker_b)

    with scope(event=event):
        result = set(feedback_for_speaker(talk, speaker_a.user))

    assert result == {own, general}


def test_feedback_for_speaker_excludes_other_talks(event):
    talk = SubmissionFactory(event=event)
    other_talk = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    talk.speakers.add(speaker)
    other_talk.speakers.add(speaker)

    own_here = FeedbackFactory(talk=talk, speaker=speaker)
    FeedbackFactory(talk=other_talk, speaker=speaker)

    with scope(event=event):
        result = list(feedback_for_speaker(talk, speaker.user))

    assert result == [own_here]


def test_feedback_for_speaker_returns_general_only_for_outsider(event):
    talk = SubmissionFactory(event=event)
    speaker = SpeakerFactory(event=event)
    talk.speakers.add(speaker)
    outsider = UserFactory()

    FeedbackFactory(talk=talk, speaker=speaker)
    general = FeedbackFactory(talk=talk, speaker=None)

    with scope(event=event):
        result = list(feedback_for_speaker(talk, outsider))

    assert result == [general]
