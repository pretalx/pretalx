# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt
from urllib.parse import quote

import pytest
from django.urls import reverse
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretalx.schedule.domain.release import freeze_schedule
from pretalx.submission.domain.signup import create_signup
from pretalx.submission.enums import AttendeeSignupStates
from pretalx.submission.models import AttendeeSignup, Submission, SubmissionStates
from tests.factories import (
    EventFactory,
    RoomFactory,
    SpeakerFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TalkSlotFactory,
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.e2e, pytest.mark.django_db]


def _build_session(event, *, capacity=2, signup_required_on_type=False):
    with scopes_disabled():
        sub_type = SubmissionTypeFactory(
            event=event, attendee_signup_required=signup_required_on_type
        )
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(
            event=event,
            submission_type=sub_type,
            state=SubmissionStates.CONFIRMED,
            attendee_signup_capacity=capacity,
        )
        submission.speakers.add(speaker)
        room = RoomFactory(event=event, capacity=20)
        TalkSlotFactory(
            submission=submission,
            room=room,
            is_visible=True,
            start=now() + dt.timedelta(hours=1),
            end=now() + dt.timedelta(hours=2),
        )
    return submission


def test_full_attendee_signup_flow(client):
    event = EventFactory()
    submission = _build_session(event)
    organiser = make_orga_user(event)

    with scopes_disabled():
        event.feature_flags = {**event.feature_flags, "attendee_signup": True}
        event.save()

    with scopes_disabled():
        Submission.objects.filter(pk=submission.pk).update(
            attendee_signup_required=True
        )
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)
    submission.refresh_from_db()

    widget_data = client.get(event.urls.schedule_widget_data).json()
    talks = [t for t in widget_data["talks"] if t["code"] == submission.code]
    assert talks, widget_data
    assert talks[0]["signup_status"] == "open"

    response = client.get(submission.urls.public, follow=True)
    assert response.status_code == 200
    content = response.content.decode()
    assert f"{event.urls.login}?next=" in content
    assert "%23signup" in content

    next_param = quote(f"{submission.urls.public}#signup")
    register_url = f"{event.urls.login}?next={next_param}"
    response = client.post(
        register_url,
        {
            "register_name": "New Attendee",
            "register_email": "newattendee@example.com",
            "register_password": "verysecure123!",
            "register_password_repeat": "verysecure123!",
        },
        follow=False,
    )
    assert response.status_code == 302
    assert "#signup" in response.url

    response = client.post(submission.urls.signup, follow=False)
    assert response.status_code == 302
    assert response.url == f"{submission.urls.public}#signup-success"
    with scope(event=event):
        signup = AttendeeSignup.objects.get(submission=submission)
        assert signup.state == AttendeeSignupStates.CONFIRMED
        assert signup.attendee.user.email == "newattendee@example.com"
        assert submission.confirmed_signup_count == 1

    with scope(event=event):
        create_signup(submission, user=UserFactory())
    widget_data = client.get(event.urls.schedule_widget_data).json()
    talk_data = next(t for t in widget_data["talks"] if t["code"] == submission.code)
    assert talk_data["signup_status"] == "full"

    response = client.get(submission.urls.public, follow=True)
    content = response.content.decode()
    assert "signup-cancel-dialog" in content
    assert "signup-success-dialog" in content
    assert submission.urls.ical in content

    client.force_login(organiser)
    orga_signup_url = reverse(
        "orga:submissions.signup", kwargs={"event": event.slug, "code": submission.code}
    )
    response = client.get(orga_signup_url)
    assert response.status_code == 200
    assert "newattendee@example.com" in response.content.decode()

    history_url = reverse(
        "orga:submissions.history",
        kwargs={"event": event.slug, "code": submission.code},
    )
    response = client.get(history_url)
    assert response.status_code == 200
    assert "An attendee signed up for the session." in response.content.decode()


def test_anonymous_user_login_preserves_signup_fragment(client, event):
    user = UserFactory(email="returning@example.com", password="goodpassword!")
    with scopes_disabled():
        event.feature_flags = {**event.feature_flags, "attendee_signup": True}
        event.save()
    submission = _build_session(event, capacity=5, signup_required_on_type=True)
    with scopes_disabled():
        freeze_schedule(event.wip_schedule, "v1", notify_speakers=False)

    next_param = quote(f"{submission.urls.public}#signup")
    login_url = f"{event.urls.login}?next={next_param}"
    response = client.post(
        login_url,
        {"login_email": user.email, "login_password": "goodpassword!"},
        follow=False,
    )

    assert response.status_code == 302
    assert "#signup" in response.url
