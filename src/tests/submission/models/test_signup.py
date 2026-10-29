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


def test_attendee_signup_logs_on_parent_submission():
    signup = AttendeeSignupFactory()
    submission = signup.submission

    with scope(event=submission.event):
        log = signup.log_action(".signup")
        signup.delete()
        action_types = [log.action_type for log in submission.logged_actions()]

    assert str(signup) == (
        f"AttendeeSignup(submission={submission.code}, "
        f"attendee={signup.attendee}, state={signup.state})"
    )
    assert signup.event == submission.event
    assert signup.log_parent == submission
    assert log.content_object == submission
    assert log.event == submission.event
    assert action_types == [
        "pretalx.submission.signup.delete",
        "pretalx.submission.signup.signup",
    ]


def test_attendee_signup_logged_actions_filters_submission_log_by_attendee():
    submission = SubmissionFactory()
    attendee_one = AttendeeProfileFactory(event=submission.event)
    attendee_two = AttendeeProfileFactory(event=submission.event)

    with scope(event=submission.event):
        signup_one = AttendeeSignup.objects.create(
            submission=submission, attendee=attendee_one
        )
        signup_two = AttendeeSignup.objects.create(
            submission=submission, attendee=attendee_two
        )
        signup_one.log_action(".signup", person=attendee_one.user)
        signup_one.log_action(".cancel", person=attendee_one.user)
        signup_two.log_action(".signup", person=attendee_two.user)
        # Unrelated submission log — must not leak in.
        submission.log_action("pretalx.submission.update", person=attendee_one.user)

        one_actions = list(signup_one.logged_actions())
        two_actions = list(signup_two.logged_actions())

    assert {log.action_type for log in one_actions} == {
        "pretalx.submission.signup.signup",
        "pretalx.submission.signup.cancel",
    }
    assert all(log.person == attendee_one.user for log in one_actions)
    assert {log.action_type for log in two_actions} == {
        "pretalx.submission.signup.signup"
    }
    assert all(log.person == attendee_two.user for log in two_actions)


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

        # ``order_queryset`` delegates to ``get_order_queryset(submission=...)``;
        # both must scope to the originating submission only.
        assert list(signup_one.order_queryset) == [signup_one, signup_two]
        assert list(AttendeeSignup.get_order_queryset(submission=submission)) == [
            signup_one,
            signup_two,
        ]
