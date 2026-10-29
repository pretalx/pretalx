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


def _messages(validator, *args, **kwargs):
    try:
        validator(*args, **kwargs)
    except ValidationError as exc:
        return exc.messages
    return []


@pytest.mark.parametrize(
    ("max_speakers", "current", "pending", "additional", "messages"),
    (
        (None, 10, 10, 10, []),
        (
            None,
            1,
            0,
            50,
            [
                (
                    "This would exceed the maximum of 50 speakers per proposal. "
                    "Currently: 1 speaker(s) and 0 pending invitation(s)."
                )
            ],
        ),
        (3, 1, 1, 1, []),
        (3, 2, 0, 1, []),
        (
            2,
            1,
            1,
            1,
            [
                (
                    "This would exceed the maximum of 2 speakers per proposal. "
                    "Currently: 1 speaker(s) and 1 pending invitation(s)."
                )
            ],
        ),
    ),
    ids=("default_backstop", "over_backstop", "within_limit", "at_limit", "over_limit"),
)
def test_validate_speakers_within_limit(
    max_speakers, current, pending, additional, messages
):
    event = EventFactory()
    event.cfp.fields["additional_speaker"]["max"] = max_speakers
    event.cfp.save()

    assert (
        _messages(
            validate_speakers_within_limit,
            event,
            current=current,
            pending=pending,
            additional=additional,
        )
        == messages
    )


def test_validate_invitation_target():
    event = EventFactory()
    event.cfp.fields["additional_speaker"]["max"] = 3
    event.cfp.save()
    speaker = SpeakerFactory(event=event)
    managed = SpeakerFactory(event=event, user=None, email="managed@example.test")
    submission = SubmissionFactory(event=event)
    empty_submission = SubmissionFactory(event=event)

    with scope(event=event):
        submission.speakers.add(speaker, managed)
        submission.invitations.create(email="invited@example.test")
        results = [
            _messages(validate_invitation_target, submission, email)
            for email in (
                speaker.user.email,
                "Managed@example.test",
                "Invited@example.test",
                "fresh@example.test",
            )
        ]
        results.append(
            _messages(
                validate_invitation_target, empty_submission, "fresh@example.test"
            )
        )

    assert results == [
        ["This person is already a speaker on this proposal."],
        ["This person is already a speaker on this proposal."],
        ["This person has already been invited to this proposal."],
        [
            (
                "This would exceed the maximum of 3 speakers per proposal. "
                "Currently: 2 speaker(s) and 1 pending invitation(s)."
            )
        ],
        [],
    ]
