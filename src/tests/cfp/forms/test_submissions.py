# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core import mail as djmail

from pretalx.cfp.forms.submissions import SubmissionInvitationForm
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


def test_invitation_form_init_populates_subject_and_text(submission_with_speaker):
    submission, speaker_user = submission_with_speaker

    form = SubmissionInvitationForm(submission=submission, speaker=speaker_user)

    assert speaker_user.get_display_name() in form.initial["subject"]
    assert str(submission.event.name) in form.initial["text"]
    assert str(submission.title) in form.initial["text"]
    assert "{invitation_url}" in form.initial["text"]


def test_invitation_form_valid_with_correct_data(submission_with_speaker):
    submission, speaker_user = submission_with_speaker

    form = SubmissionInvitationForm(
        submission=submission,
        speaker=speaker_user,
        data={
            "speaker": "new-speaker@example.com",
            "subject": "You're invited!",
            "text": "Join us at {invitation_url} please!",
        },
    )
    assert form.is_valid(), form.errors


@pytest.mark.parametrize(
    "text", ("Join us please!", ""), ids=("missing_placeholder", "empty")
)
def test_invitation_form_clean_text_rejects_invalid_text(submission_with_speaker, text):
    submission, speaker_user = submission_with_speaker

    form = SubmissionInvitationForm(
        submission=submission,
        speaker=speaker_user,
        data={"speaker": "new-speaker@example.com", "subject": "Invite", "text": text},
    )
    assert not form.is_valid()
    assert "text" in form.errors


@pytest.mark.parametrize("upcase", (False, True), ids=("exact", "case_insensitive"))
def test_invitation_form_clean_speaker_rejects_existing_speaker(
    submission_with_speaker, upcase
):
    submission, speaker_user = submission_with_speaker
    email = speaker_user.email.upper() if upcase else speaker_user.email

    form = SubmissionInvitationForm(
        submission=submission,
        speaker=speaker_user,
        data={
            "speaker": email,
            "subject": "Invite",
            "text": "Join at {invitation_url}",
        },
    )
    assert not form.is_valid()
    assert "speaker" in form.errors


@pytest.mark.parametrize("upcase", (False, True), ids=("exact", "case_insensitive"))
def test_invitation_form_clean_speaker_rejects_already_invited(
    submission_with_speaker, upcase
):
    submission, speaker_user = submission_with_speaker
    SubmissionInvitationFactory(submission=submission, email="invited@example.com")
    email = "INVITED@example.com" if upcase else "invited@example.com"
    form = SubmissionInvitationForm(
        submission=submission,
        speaker=speaker_user,
        data={
            "speaker": email,
            "subject": "Invite",
            "text": "Join at {invitation_url}",
        },
    )
    assert not form.is_valid()
    assert "speaker" in form.errors


def test_invitation_form_clean_speaker_lowercases_and_strips(submission_with_speaker):
    submission, speaker_user = submission_with_speaker

    form = SubmissionInvitationForm(
        submission=submission,
        speaker=speaker_user,
        data={
            "speaker": "  NewSpeaker@Example.COM  ",
            "subject": "Invite",
            "text": "Join at {invitation_url}",
        },
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["speaker"] == "newspeaker@example.com"


def test_invitation_form_clean_speaker_rejects_exceeding_max_speakers():
    submission, speaker_user = _create_submission_with_speaker(
        cfp__fields={"additional_speaker": {"visibility": "required", "max": 1}}
    )

    form = SubmissionInvitationForm(
        submission=submission,
        speaker=speaker_user,
        data={
            "speaker": "extra@example.com",
            "subject": "Invite",
            "text": "Join at {invitation_url}",
        },
    )
    assert not form.is_valid()
    assert "speaker" in form.errors


def test_invitation_form_clean_speaker_allows_within_max_speakers():
    submission, speaker_user = _create_submission_with_speaker(
        cfp__fields={"additional_speaker": {"visibility": "required", "max": 3}}
    )

    form = SubmissionInvitationForm(
        submission=submission,
        speaker=speaker_user,
        data={
            "speaker": "extra@example.com",
            "subject": "Invite",
            "text": "Join at {invitation_url}",
        },
    )
    assert form.is_valid(), form.errors


def test_invitation_form_clean_speaker_counts_pending_invitations_toward_max():
    submission, speaker_user = _create_submission_with_speaker(
        cfp__fields={"additional_speaker": {"visibility": "required", "max": 2}}
    )
    SubmissionInvitationFactory(submission=submission, email="pending@example.com")

    form = SubmissionInvitationForm(
        submission=submission,
        speaker=speaker_user,
        data={
            "speaker": "extra@example.com",
            "subject": "Invite",
            "text": "Join at {invitation_url}",
        },
    )
    assert not form.is_valid()
    assert "speaker" in form.errors


def test_invitation_form_save_creates_invitation_and_sends_email(
    submission_with_speaker,
):
    djmail.outbox = []
    submission, speaker_user = submission_with_speaker

    form = SubmissionInvitationForm(
        submission=submission,
        speaker=speaker_user,
        data={
            "speaker": "new-speaker@example.com",
            "subject": "You're invited!",
            "text": "Join us at {invitation_url} please!",
        },
    )
    assert form.is_valid(), form.errors
    invitation = form.save()

    assert invitation.pk is not None
    assert invitation.submission == submission
    assert invitation.email == "new-speaker@example.com"
    assert len(djmail.outbox) == 1
    assert djmail.outbox[0].to == ["new-speaker@example.com"]
    assert "You're invited!" in djmail.outbox[0].subject


def test_invitation_form_save_replaces_placeholder_in_text(submission_with_speaker):
    djmail.outbox = []
    submission, speaker_user = submission_with_speaker

    form = SubmissionInvitationForm(
        submission=submission,
        speaker=speaker_user,
        data={
            "speaker": "new-speaker@example.com",
            "subject": "Invite",
            "text": "Click here: {invitation_url} to join.",
        },
    )
    assert form.is_valid(), form.errors
    invitation = form.save()

    assert len(djmail.outbox) == 1
    body = djmail.outbox[0].body
    assert "{invitation_url}" not in body
    assert invitation.token in body


def test_invitation_form_save_returns_existing_without_resending(
    submission_with_speaker,
):
    djmail.outbox = []
    submission, speaker_user = submission_with_speaker
    existing = SubmissionInvitationFactory(
        submission=submission, email="repeat@example.com"
    )

    form = SubmissionInvitationForm(
        submission=submission,
        speaker=speaker_user,
        data={
            "speaker": "repeat@example.com",
            "subject": "Invite",
            "text": "Join at {invitation_url}",
        },
    )
    form.cleaned_data = {
        "speaker": "repeat@example.com",
        "subject": "Invite",
        "text": "Join at {invitation_url}",
    }

    result = form.save()

    assert result == existing
    assert len(djmail.outbox) == 0
