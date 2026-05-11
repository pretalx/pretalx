# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.person.interfaces.forms import SubmissionInvitationForm
from tests.factories import (
    SpeakerFactory,
    SubmissionFactory,
    SubmissionInvitationFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _create_submission_with_speaker(**event_kwargs):
    """Create a submission with one speaker attached, returning (submission, speaker_user).

    Any keyword arguments are forwarded to the EventFactory via SubmissionFactory
    (e.g. cfp__fields={"additional_speaker": {"visibility": "required", "max": 3}}).
    """
    submission = SubmissionFactory(
        **{f"event__{k}": v for k, v in event_kwargs.items()}
    )
    speaker_profile = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker_profile)
    return submission, speaker_profile.user


@pytest.fixture
def submission_with_speaker():
    """A submission with one speaker attached, returning (submission, speaker_user)."""
    return _create_submission_with_speaker()


def test_invitation_form_valid_with_correct_data(submission_with_speaker):
    submission, _ = submission_with_speaker

    form = SubmissionInvitationForm(
        submission=submission, data={"speaker": "new-speaker@example.com"}
    )
    assert form.is_valid(), form.errors


@pytest.mark.parametrize("upcase", (False, True), ids=("exact", "case_insensitive"))
def test_invitation_form_clean_speaker_rejects_existing_speaker(
    submission_with_speaker, upcase
):
    submission, speaker_user = submission_with_speaker
    email = speaker_user.email.upper() if upcase else speaker_user.email

    form = SubmissionInvitationForm(submission=submission, data={"speaker": email})
    assert not form.is_valid()
    assert "speaker" in form.errors


@pytest.mark.parametrize("upcase", (False, True), ids=("exact", "case_insensitive"))
def test_invitation_form_clean_speaker_rejects_already_invited(
    submission_with_speaker, upcase
):
    submission, _ = submission_with_speaker
    SubmissionInvitationFactory(submission=submission, email="invited@example.com")
    email = "INVITED@example.com" if upcase else "invited@example.com"
    form = SubmissionInvitationForm(submission=submission, data={"speaker": email})
    assert not form.is_valid()
    assert "speaker" in form.errors


def test_invitation_form_clean_speaker_lowercases_and_strips(submission_with_speaker):
    submission, _ = submission_with_speaker

    form = SubmissionInvitationForm(
        submission=submission, data={"speaker": "  NewSpeaker@Example.COM  "}
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["speaker"] == "newspeaker@example.com"


def test_invitation_form_clean_speaker_rejects_exceeding_max_speakers():
    submission, _ = _create_submission_with_speaker(
        cfp__fields={"additional_speaker": {"visibility": "required", "max": 1}}
    )

    form = SubmissionInvitationForm(
        submission=submission, data={"speaker": "extra@example.com"}
    )
    assert not form.is_valid()
    assert "speaker" in form.errors


def test_invitation_form_clean_speaker_allows_within_max_speakers():
    submission, _ = _create_submission_with_speaker(
        cfp__fields={"additional_speaker": {"visibility": "required", "max": 3}}
    )

    form = SubmissionInvitationForm(
        submission=submission, data={"speaker": "extra@example.com"}
    )
    assert form.is_valid(), form.errors


def test_invitation_form_clean_speaker_counts_pending_invitations_toward_max():
    submission, _ = _create_submission_with_speaker(
        cfp__fields={"additional_speaker": {"visibility": "required", "max": 2}}
    )
    SubmissionInvitationFactory(submission=submission, email="pending@example.com")

    form = SubmissionInvitationForm(
        submission=submission, data={"speaker": "extra@example.com"}
    )
    assert not form.is_valid()
    assert "speaker" in form.errors
