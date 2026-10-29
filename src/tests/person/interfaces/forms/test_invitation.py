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
    submission = SubmissionFactory(
        **{f"event__{k}": v for k, v in event_kwargs.items()}
    )
    speaker_profile = SpeakerFactory(event=submission.event)
    submission.speakers.add(speaker_profile)
    return submission, speaker_profile.user


def test_invitation_form_clean_speaker_lowercases_and_strips():
    submission, _ = _create_submission_with_speaker()

    form = SubmissionInvitationForm(
        submission=submission, data={"speaker": "  NewSpeaker@Example.COM  "}
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["speaker"] == "newspeaker@example.com"


@pytest.mark.parametrize(
    ("kind", "upcase"),
    (("speaker", False), ("speaker", True), ("invited", False), ("invited", True)),
    ids=(
        "speaker_exact",
        "speaker_case_insensitive",
        "invited_exact",
        "invited_case_insensitive",
    ),
)
def test_invitation_form_clean_speaker_rejects_present_and_invited_speakers(
    kind, upcase
):
    submission, speaker_user = _create_submission_with_speaker()
    SubmissionInvitationFactory(submission=submission, email="invited@example.com")
    email = {"speaker": speaker_user.email, "invited": "invited@example.com"}[kind]
    if upcase:
        email = email.upper()

    form = SubmissionInvitationForm(submission=submission, data={"speaker": email})

    assert not form.is_valid()
    assert list(form.errors) == ["speaker"]


@pytest.mark.parametrize(
    ("max_speakers", "valid"), ((2, False), (3, True)), ids=("at_max", "below_max")
)
def test_invitation_form_clean_speaker_counts_speakers_and_pending_invitations(
    max_speakers, valid
):
    submission, _ = _create_submission_with_speaker(
        cfp__fields={
            "additional_speaker": {"visibility": "required", "max": max_speakers}
        }
    )
    SubmissionInvitationFactory(submission=submission, email="pending@example.com")

    form = SubmissionInvitationForm(
        submission=submission, data={"speaker": "extra@example.com"}
    )

    assert form.is_valid() is valid, form.errors
    assert list(form.errors) == ([] if valid else ["speaker"])
