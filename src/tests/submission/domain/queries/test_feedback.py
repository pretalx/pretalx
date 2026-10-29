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


def test_feedback_for_speaker_returns_own_and_general_on_this_talk(event):
    talk = SubmissionFactory(event=event)
    other_talk = SubmissionFactory(event=event)
    speaker_a = SpeakerFactory(event=event)
    speaker_b = SpeakerFactory(event=event)
    talk.speakers.add(speaker_a, speaker_b)
    other_talk.speakers.add(speaker_a)
    outsider = UserFactory()

    own = FeedbackFactory(talk=talk, speaker=speaker_a)
    general = FeedbackFactory(talk=talk, speaker=None)
    for_b = FeedbackFactory(talk=talk, speaker=speaker_b)
    FeedbackFactory(talk=other_talk, speaker=speaker_a)

    with scope(event=event):
        assert set(feedback_for_speaker(talk, speaker_a.user)) == {own, general}
        assert set(feedback_for_speaker(talk, speaker_b.user)) == {for_b, general}
        assert list(feedback_for_speaker(talk, outsider)) == [general]
