# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.contrib.auth.models import AnonymousUser
from django_scopes import scope

from pretalx.common.exceptions import SubmissionError
from pretalx.schedule.domain.release import freeze_schedule
from pretalx.submission.domain.signup import (
    can_user_signup,
    cancel_signup,
    create_signup,
    email_domain_allowed,
    get_confirmed_signup_for_user,
    get_signup_for_user,
)
from pretalx.submission.enums import AttendeeSignupStates
from pretalx.submission.models import AttendeeSignup, SubmissionStates
from tests.factories import (
    AttendeeProfileFactory,
    AttendeeSignupFactory,
    EventFactory,
    RoomFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TalkSlotFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _signup_event(**event_kwargs):
    flags = event_kwargs.pop("feature_flags", {})
    flags = {"attendee_signup": True, **flags}
    event = EventFactory(feature_flags=flags, **event_kwargs)
    sub_type = SubmissionTypeFactory(event=event, attendee_signup_required=True)
    return event, sub_type


def _make_submission(event, sub_type, *, capacity=10):
    return SubmissionFactory(
        event=event, submission_type=sub_type, attendee_signup_capacity=capacity
    )


def _signup_error(submission, user):
    try:
        create_signup(submission, user=user)
    except SubmissionError as exc:
        return str(exc)
    return None


@pytest.mark.parametrize(
    ("settings", "email", "expected"),
    (
        ({"signup_domains": []}, "user@example.com", True),
        ({"signup_domains": None}, "user@example.com", True),
        ({}, "user@example.com", True),
        (None, "user@example.com", True),
        ({"signup_domains": ["example.com"]}, "user@example.com", True),
        ({"signup_domains": ["example.com"]}, "user@EXAMPLE.com", True),
        ({"signup_domains": ["EXAMPLE.com"]}, "user@example.com", True),
        ({"signup_domains": ["example.com", "other.com"]}, "user@other.com", True),
        ({"signup_domains": ["example.com"]}, "user@evil.com", False),
        ({"signup_domains": ["example.com"]}, "", False),
        ({"signup_domains": ["example.com"]}, "no-at-sign", False),
    ),
    ids=(
        "no-restriction-empty-list",
        "no-restriction-none",
        "no-restriction-missing-key",
        "no-restriction-missing-settings",
        "match",
        "match-case-insensitive-email",
        "match-case-insensitive-domain",
        "match-second-domain",
        "no-match",
        "empty-email",
        "malformed-email",
    ),
)
def test_email_domain_allowed_handles_all_cases(settings, email, expected):
    event = EventFactory()
    event.attendee_signup_settings = settings

    assert email_domain_allowed(event, email) is expected


@pytest.mark.parametrize(
    ("feature", "type_required", "user_email", "allowed_domain", "error"),
    (
        (
            False,
            True,
            "u@example.com",
            None,
            "Attendee signup is not enabled for this event.",
        ),
        (
            True,
            False,
            "u@example.com",
            None,
            "This session does not require attendee signup.",
        ),
        (
            True,
            True,
            "user@forbidden.example",
            "allowed.example",
            "You cannot sign up for this session.",
        ),
        (True, True, "ok@allowed.example", "allowed.example", None),
    ),
    ids=(
        "feature_disabled",
        "session_does_not_require_signup",
        "email_domain_blocked",
        "all_checks_pass",
    ),
)
def test_can_user_signup_and_create_signup_gate(
    feature, type_required, user_email, allowed_domain, error
):
    event_kwargs = {"feature_flags": {"attendee_signup": feature}}
    if allowed_domain:
        event_kwargs["attendee_signup_settings"] = {"signup_domains": [allowed_domain]}
    event = EventFactory(**event_kwargs)
    sub_type = SubmissionTypeFactory(
        event=event, attendee_signup_required=type_required
    )
    submission = SubmissionFactory(event=event, submission_type=sub_type)
    user = UserFactory(email=user_email)

    with scope(event=event):
        assert can_user_signup(submission, AnonymousUser()) is False
        assert can_user_signup(submission, None) is False
        assert can_user_signup(submission, user) is (error is None)
        assert _signup_error(submission, user) == error


def test_get_signup_for_user_in_any_state_and_confirmed_only():
    signup = AttendeeSignupFactory(state=AttendeeSignupStates.CANCELED)
    submission = signup.submission
    user = signup.attendee.user

    with scope(event=submission.event):
        assert get_signup_for_user(submission, AnonymousUser()) is None
        assert get_signup_for_user(submission, None) is None
        assert get_signup_for_user(submission, user) == signup
        assert get_confirmed_signup_for_user(submission, user) is None
        assert get_confirmed_signup_for_user(submission, UserFactory()) is None

        signup.state = AttendeeSignupStates.CONFIRMED
        signup.save()

        assert get_confirmed_signup_for_user(submission, user) == signup


def test_create_and_cancel_signup_chain():
    event, sub_type = _signup_event()
    submission = _make_submission(event, sub_type, capacity=None)
    user = UserFactory(email="attendee@example.com")
    profile = AttendeeProfileFactory(event=event, user=user)
    signup_logs = submission.logged_actions().filter(
        action_type="pretalx.submission.signup.signup"
    )
    cancel_logs = submission.logged_actions().filter(
        action_type="pretalx.submission.signup.cancel"
    )

    with scope(event=event):
        assert cancel_signup(submission, user=user) is None

        signup = create_signup(submission, user=user)

        assert signup.state == AttendeeSignupStates.CONFIRMED
        assert signup.attendee.pk == profile.pk
        assert signup.attendee.user_id == user.pk
        assert signup.attendee.event_id == event.pk
        assert submission.confirmed_signup_count == 1
        log = signup_logs.get()
        assert log.person == user
        assert log.content_object == submission

        assert create_signup(submission, user=user).pk == signup.pk
        assert AttendeeSignup.objects.filter(submission=submission).count() == 1
        assert signup_logs.count() == 1

        cancelled = cancel_signup(submission, user=user)

        assert cancelled.pk == signup.pk
        assert cancelled.state == AttendeeSignupStates.CANCELED
        assert cancel_logs.count() == 1
        assert cancel_signup(submission, user=user) is None
        assert cancel_logs.count() == 1

        reactivated = create_signup(submission, user=user)

        assert reactivated.pk == signup.pk
        assert reactivated.state == AttendeeSignupStates.CONFIRMED
        assert signup_logs.count() == 2
        assert AttendeeSignup.objects.filter(submission=submission).count() == 1


def test_create_signup_raises_when_capacity_reached():
    event, sub_type = _signup_event()
    submission = _make_submission(event, sub_type, capacity=1)
    existing_user = UserFactory()
    new_user = UserFactory()

    with scope(event=event):
        create_signup(submission, user=existing_user)
        assert _signup_error(submission, new_user) == "This session is currently full."
        assert submission.confirmed_signup_count == 1


def test_create_signup_falls_back_to_room_capacity():
    event, sub_type = _signup_event()
    submission = SubmissionFactory(
        event=event, submission_type=sub_type, state=SubmissionStates.CONFIRMED
    )
    with scope(event=event):
        room = RoomFactory(event=event, capacity=1)
        TalkSlotFactory(
            submission=submission,
            room=room,
            schedule=event.wip_schedule,
            is_visible=True,
        )
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
    user_one = UserFactory()
    user_two = UserFactory()

    with scope(event=event):
        create_signup(submission, user=user_one)
        with pytest.raises(SubmissionError):
            create_signup(submission, user=user_two)
