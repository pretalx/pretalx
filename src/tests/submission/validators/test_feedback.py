# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError

from pretalx.submission.validators.feedback import validate_speaker_on_talk
from tests.factories import SpeakerFactory, SubmissionFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_validate_speaker_on_talk_accepts_speaker_of_talk():
    submission = SubmissionFactory()
    speaker = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker)

    validate_speaker_on_talk(submission, speaker)


def test_validate_speaker_on_talk_rejects_unrelated_speaker():
    submission = SubmissionFactory()
    other_speaker = SpeakerFactory(event=submission.event)

    with pytest.raises(ValidationError) as exc_info:
        validate_speaker_on_talk(submission, other_speaker)

    assert "speaker" in exc_info.value.message_dict


def test_validate_speaker_on_talk_allows_no_speaker():
    submission = SubmissionFactory()

    validate_speaker_on_talk(submission, None)
