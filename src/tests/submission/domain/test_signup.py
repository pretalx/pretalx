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


@pytest.mark.parametrize(
    ("domains", "email", "expected"),
    (
        ([], "user@example.com", True),
        (None, "user@example.com", True),
        (["example.com"], "user@example.com", True),
        (["example.com"], "user@EXAMPLE.com", True),
        (["EXAMPLE.com"], "user@example.com", True),
        (["example.com", "other.com"], "user@other.com", True),
        (["example.com"], "user@evil.com", False),
        (["example.com"], "", False),
        (["example.com"], "no-at-sign", False),
    ),
    ids=(
        "no-restriction-empty-list",
        "no-restriction-none",
        "match",
        "match-case-insensitive-email",
        "match-case-insensitive-domain",
        "match-second-domain",
        "no-match",
        "empty-email",
        "malformed-email",
    ),
)
def test_email_domain_allowed_handles_all_cases(domains, email, expected):
    event = EventFactory(attendee_signup_settings={"signup_domains": domains or []})

    assert email_domain_allowed(event, email) is expected


def test_email_domain_allowed_handles_missing_settings():
    event = EventFactory()
    event.attendee_signup_settings = None

    assert email_domain_allowed(event, "user@example.com") is True


@pytest.mark.parametrize("user", (AnonymousUser(), None), ids=("anonymous", "none"))
def test_can_user_signup_false_for_unauthenticated(user):
    event, sub_type = _signup_event()
    submission = _make_submission(event, sub_type)

    with scope(event=event):
        assert can_user_signup(submission, user) is False


@pytest.mark.parametrize(
    ("feature", "type_required", "user_email", "allowed_domain", "expected"),
    (
        (False, True, "u@example.com", None, False),
        (True, False, "u@example.com", None, False),
        (True, True, "user@forbidden.example", "allowed.example", False),
        (True, True, "ok@allowed.example", "allowed.example", True),
    ),
    ids=(
        "feature_disabled",
        "session_does_not_require_signup",
        "email_domain_blocked",
        "all_checks_pass",
    ),
)
def test_can_user_signup_authenticated(
    feature, type_required, user_email, allowed_domain, expected
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
        assert can_user_signup(submission, user) is expected


@pytest.mark.parametrize("user", (AnonymousUser(), None), ids=("anonymous", "none"))
def test_get_signup_for_user_returns_none_for_unauthenticated(user):
    submission = SubmissionFactory()

    assert get_signup_for_user(submission, user) is None


def test_get_signup_for_user_returns_signup_in_any_state():
    signup = AttendeeSignupFactory(state=AttendeeSignupStates.CANCELED)

    with scope(event=signup.submission.event):
        result = get_signup_for_user(signup.submission, signup.attendee.user)
        assert result == signup


@pytest.mark.parametrize(
    ("state", "expect_match"),
    ((AttendeeSignupStates.CONFIRMED, True), (AttendeeSignupStates.CANCELED, False)),
    ids=("confirmed", "cancelled"),
)
def test_get_confirmed_signup_for_user(state, expect_match):
    signup = AttendeeSignupFactory(state=state)

    with scope(event=signup.submission.event):
        result = get_confirmed_signup_for_user(signup.submission, signup.attendee.user)
        assert result == (signup if expect_match else None)


def test_get_confirmed_signup_for_user_returns_none_when_no_signup():
    submission = SubmissionFactory()
    user = UserFactory()

    with scope(event=submission.event):
        assert get_confirmed_signup_for_user(submission, user) is None


def test_create_signup_creates_attendee_profile_and_signup():
    event, sub_type = _signup_event()
    submission = _make_submission(event, sub_type)
    user = UserFactory(email="attendee@example.com")

    with scope(event=event):
        signup = create_signup(submission, user=user)

        assert signup.state == AttendeeSignupStates.CONFIRMED
        assert signup.attendee.user == user
        assert signup.attendee.event == event
        assert submission.confirmed_signup_count == 1


def test_create_signup_logs_with_submission_as_target():
    event, sub_type = _signup_event()
    submission = _make_submission(event, sub_type)
    user = UserFactory()

    with scope(event=event):
        create_signup(submission, user=user)
        logs = list(
            submission.logged_actions().filter(
                action_type="pretalx.submission.signup.signup"
            )
        )
        assert len(logs) == 1
        assert logs[0].person == user
        assert logs[0].content_object == submission


def test_create_signup_is_idempotent_when_already_confirmed():
    event, sub_type = _signup_event()
    submission = _make_submission(event, sub_type)
    user = UserFactory()

    with scope(event=event):
        first = create_signup(submission, user=user)
        second = create_signup(submission, user=user)

        assert first.pk == second.pk
        assert AttendeeSignup.objects.filter(submission=submission).count() == 1
        assert (
            submission.logged_actions()
            .filter(action_type="pretalx.submission.signup.signup")
            .count()
            == 1
        )


def test_create_signup_reactivates_cancelled_signup():
    event, sub_type = _signup_event()
    submission = _make_submission(event, sub_type)
    user = UserFactory()

    with scope(event=event):
        first = create_signup(submission, user=user)
        cancel_signup(submission, user=user)
        reactivated = create_signup(submission, user=user)

        assert reactivated.pk == first.pk
        assert reactivated.state == AttendeeSignupStates.CONFIRMED
        assert (
            submission.logged_actions()
            .filter(action_type="pretalx.submission.signup.signup")
            .count()
            == 2
        )
        assert (
            submission.logged_actions()
            .filter(action_type="pretalx.submission.signup.cancel")
            .count()
            == 1
        )


@pytest.mark.parametrize(
    ("feature", "type_required", "user_email", "allowed_domain"),
    (
        (False, True, "u@example.com", None),
        (True, False, "u@example.com", None),
        (True, True, "user@forbidden.example", "allowed.example"),
    ),
    ids=("feature_disabled", "session_does_not_require_signup", "email_domain_blocked"),
)
def test_create_signup_raises_when_gate_fails(
    feature, type_required, user_email, allowed_domain
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

    with scope(event=event), pytest.raises(SubmissionError):
        create_signup(submission, user=user)


def test_create_signup_raises_when_capacity_reached():
    event, sub_type = _signup_event()
    submission = _make_submission(event, sub_type, capacity=1)
    existing_user = UserFactory()
    new_user = UserFactory()

    with scope(event=event):
        create_signup(submission, user=existing_user)
        with pytest.raises(SubmissionError):
            create_signup(submission, user=new_user)
        assert submission.confirmed_signup_count == 1


def test_create_signup_with_unlimited_capacity_succeeds():
    event, sub_type = _signup_event()
    submission = SubmissionFactory(
        event=event, submission_type=sub_type, attendee_signup_capacity=None
    )
    user = UserFactory()

    with scope(event=event):
        signup = create_signup(submission, user=user)
        assert signup.state == AttendeeSignupStates.CONFIRMED


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


def test_create_signup_existing_attendee_profile_is_reused():
    event, sub_type = _signup_event()
    submission = _make_submission(event, sub_type)
    user = UserFactory()
    profile = AttendeeProfileFactory(event=event, user=user)

    with scope(event=event):
        signup = create_signup(submission, user=user)

        assert signup.attendee.pk == profile.pk


def test_cancel_signup_returns_none_when_no_signup():
    submission = SubmissionFactory()
    user = UserFactory()

    with scope(event=submission.event):
        assert cancel_signup(submission, user=user) is None


def test_cancel_signup_is_idempotent_on_already_cancelled():
    signup = AttendeeSignupFactory(state=AttendeeSignupStates.CANCELED)

    with scope(event=signup.submission.event):
        result = cancel_signup(signup.submission, user=signup.attendee.user)
        assert result is None


def test_cancel_signup_sets_state_and_logs():
    event, sub_type = _signup_event()
    submission = _make_submission(event, sub_type)
    user = UserFactory()

    with scope(event=event):
        create_signup(submission, user=user)
        cancelled = cancel_signup(submission, user=user)

        assert cancelled.state == AttendeeSignupStates.CANCELED
        assert (
            submission.logged_actions()
            .filter(action_type="pretalx.submission.signup.cancel")
            .count()
            == 1
        )
