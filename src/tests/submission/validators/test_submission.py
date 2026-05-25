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


def test_validate_slot_count_allows_one():
    event = EventFactory()
    validate_slot_count(1, event=event)  # does not raise


def test_validate_slot_count_blocks_above_one_without_feature_flag():
    event = EventFactory(feature_flags={"present_multiple_times": False})
    with pytest.raises(ValidationError):
        validate_slot_count(2, event=event)


def test_validate_slot_count_allows_above_one_with_feature_flag():
    event = EventFactory(feature_flags={"present_multiple_times": True})
    validate_slot_count(3, event=event)


def test_validate_signup_required_unsaved_submission_short_circuits():
    event = EventFactory()
    sub_type = SubmissionTypeFactory(event=event)
    submission = Submission(event=event, submission_type=sub_type, title="t")
    validate_signup_required(submission, False)  # does not raise


@pytest.mark.parametrize("value", (True, None), ids=("true", "none"))
def test_validate_signup_required_non_false_passes_with_signups(value):
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        AttendeeSignupFactory(submission=submission)
        validate_signup_required(submission, value)


def test_validate_signup_required_false_raises_with_signups():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        AttendeeSignupFactory(submission=submission)
        with pytest.raises(ValidationError) as exc:
            validate_signup_required(submission, False)
    assert "attendee_signup_required" in exc.value.message_dict


def test_validate_signup_required_false_passes_without_signups():
    submission = SubmissionFactory()
    validate_signup_required(submission, False)


def test_validate_signup_required_ignores_canceled_signups():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    with scope(event=event):
        AttendeeSignupFactory(
            submission=submission, state=AttendeeSignupStates.CANCELED
        )
        validate_signup_required(submission, False)  # does not raise


def test_validate_signup_required_no_op_when_value_already_false():
    event = EventFactory()
    submission = SubmissionFactory(event=event, attendee_signup_required=False)
    with scope(event=event):
        AttendeeSignupFactory(submission=submission)
        validate_signup_required(submission, False)
