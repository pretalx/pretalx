# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.exceptions import ValidationError
from django_scopes import scope

from pretalx.submission.enums import AttendeeSignupStates
from pretalx.submission.models import Submission
from pretalx.submission.validators.submission import (
    validate_signup_required,
    validate_slot_count,
)
from tests.factories import (
    AttendeeSignupFactory,
    EventFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _message_dict(validator, *args, **kwargs):
    try:
        validator(*args, **kwargs)
    except ValidationError as exc:
        return exc.message_dict
    return {}


def test_validate_slot_count_needs_feature_flag_above_one():
    without_flag = EventFactory(feature_flags={"present_multiple_times": False})
    with_flag = EventFactory(feature_flags={"present_multiple_times": True})

    validate_slot_count(1, event=without_flag)
    validate_slot_count(3, event=with_flag)
    with pytest.raises(ValidationError, match="may only be 1"):
        validate_slot_count(2, event=without_flag)


def test_validate_signup_required_blocks_disabling_only_with_confirmed_signups():
    event = EventFactory()
    unsaved = Submission(
        event=event, submission_type=SubmissionTypeFactory(event=event), title="t"
    )
    signed_up = SubmissionFactory(event=event)
    canceled_only = SubmissionFactory(event=event)
    without_signups = SubmissionFactory(event=event)
    already_disabled = SubmissionFactory(event=event, attendee_signup_required=False)
    error = {
        "attendee_signup_required": [
            "You cannot disable signup for this session while it still has attendee signups."
        ]
    }

    with scope(event=event):
        AttendeeSignupFactory(submission=signed_up)
        AttendeeSignupFactory(submission=already_disabled)
        AttendeeSignupFactory(
            submission=canceled_only, state=AttendeeSignupStates.CANCELED
        )
        results = [
            _message_dict(validate_signup_required, submission, value)
            for submission, value in (
                (unsaved, False),
                (signed_up, True),
                (signed_up, None),
                (signed_up, False),
                (canceled_only, False),
                (without_signups, False),
                (already_disabled, False),
            )
        ]

    assert results == [{}, {}, {}, error, {}, {}, {}]
