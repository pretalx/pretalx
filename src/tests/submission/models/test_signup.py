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


def test_attendee_signup_log_action_routes_content_object_to_submission():
    signup = AttendeeSignupFactory()

    with scope(event=signup.submission.event):
        log = signup.log_action(".signup")

    assert log.content_object == signup.submission
    assert log.event == signup.submission.event


def test_attendee_signup_event_resolves_through_submission():
    signup = AttendeeSignupFactory()

    assert signup.event == signup.submission.event
    assert signup.log_parent == signup.submission


def test_attendee_signup_delete_logs_on_parent_submission():
    signup = AttendeeSignupFactory()
    submission = signup.submission

    with scope(event=submission.event):
        signup.delete()
        logs = list(submission.logged_actions())

    assert any(log.action_type == "pretalx.submission.signup.delete" for log in logs)


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
