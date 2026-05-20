# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scope

from pretalx.submission.models import AttendeeSignup
from tests.factories import (
    AttendeeProfileFactory,
    AttendeeSignupFactory,
    SubmissionFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_attendee_signup_str():
    signup = AttendeeSignupFactory()

    expected = (
        f"AttendeeSignup(submission={signup.submission.code}, "
        f"attendee={signup.attendee}, state={signup.state})"
    )
    assert str(signup) == expected


def test_attendee_signup_log_parent_is_submission():
    signup = AttendeeSignupFactory()

    assert signup.log_parent == signup.submission


def test_attendee_signup_order_queryset_scoped_to_submission():
    submission = SubmissionFactory()
    other_submission = SubmissionFactory(event=submission.event)
    attendee_one = AttendeeProfileFactory(event=submission.event)
    attendee_two = AttendeeProfileFactory(event=submission.event)
    attendee_other = AttendeeProfileFactory(event=submission.event)

    with scope(event=submission.event):
        signup_one = AttendeeSignup.objects.create(
            submission=submission, attendee=attendee_one, position=0
        )
        signup_two = AttendeeSignup.objects.create(
            submission=submission, attendee=attendee_two, position=1
        )
        AttendeeSignup.objects.create(
            submission=other_submission, attendee=attendee_other, position=0
        )

        assert list(signup_one.order_queryset) == [signup_one, signup_two]


def test_attendee_signup_get_order_queryset_filters_by_submission():
    submission = SubmissionFactory()
    other_submission = SubmissionFactory(event=submission.event)
    attendee = AttendeeProfileFactory(event=submission.event)
    other_attendee = AttendeeProfileFactory(event=submission.event)

    with scope(event=submission.event):
        signup = AttendeeSignup.objects.create(
            submission=submission, attendee=attendee, position=0
        )
        AttendeeSignup.objects.create(
            submission=other_submission, attendee=other_attendee, position=0
        )

        assert list(AttendeeSignup.get_order_queryset(submission=submission)) == [
            signup
        ]
