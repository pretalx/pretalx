# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError
from django_scopes import scope

from pretalx.submission.validators.speaker import (
    validate_invitation_target,
    validate_speakers_within_limit,
)
from tests.factories import EventFactory, SpeakerFactory, SubmissionFactory

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_validate_speakers_within_limit_no_max_set_uses_default_backstop():
    event = EventFactory()
    assert event.cfp.max_speakers is None

    validate_speakers_within_limit(event, current=10, pending=10, additional=10)

    with pytest.raises(ValidationError):
        validate_speakers_within_limit(event, current=1, pending=0, additional=50)


def test_validate_speakers_within_limit_within_limit_passes():
    event = EventFactory()
    event.cfp.fields["additional_speaker"]["max"] = 3
    event.cfp.save()

    validate_speakers_within_limit(event, current=1, pending=1, additional=1)


def test_validate_speakers_within_limit_at_limit_passes():
    event = EventFactory()
    event.cfp.fields["additional_speaker"]["max"] = 3
    event.cfp.save()

    validate_speakers_within_limit(event, current=2, pending=0, additional=1)


def test_validate_speakers_within_limit_over_limit_raises():
    event = EventFactory()
    event.cfp.fields["additional_speaker"]["max"] = 2
    event.cfp.save()

    with pytest.raises(ValidationError) as exc_info:
        validate_speakers_within_limit(event, current=1, pending=1, additional=1)

    assert "maximum" in exc_info.value.messages[0].lower()


def test_validate_speakers_within_limit_counts_pending_invitations():
    event = EventFactory()
    event.cfp.fields["additional_speaker"]["max"] = 2
    event.cfp.save()

    with pytest.raises(ValidationError):
        validate_speakers_within_limit(event, current=1, pending=1, additional=1)


def test_validate_invitation_target_rejects_existing_speaker():
    event = EventFactory()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        submission.speakers.add(speaker)
        with pytest.raises(ValidationError) as exc_info:
            validate_invitation_target(submission, speaker.user.email)
    assert "already a speaker" in exc_info.value.messages[0].lower()


def test_validate_invitation_target_rejects_pending_invitation():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    email = "invited@example.test"
    with scope(event=event):
        submission.invitations.create(email=email)
        with pytest.raises(ValidationError) as exc_info:
            validate_invitation_target(submission, email)
    assert "already been invited" in exc_info.value.messages[0].lower()


def test_validate_invitation_target_enforces_limit():
    event = EventFactory()
    event.cfp.fields["additional_speaker"]["max"] = 1
    event.cfp.save()
    speaker = SpeakerFactory(event=event)
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        submission.speakers.add(speaker)
        with pytest.raises(ValidationError) as exc_info:
            validate_invitation_target(submission, "fresh@example.test")
    assert "maximum" in exc_info.value.messages[0].lower()


def test_validate_invitation_target_passes_for_new_email():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        validate_invitation_target(submission, "newbie@example.test")
