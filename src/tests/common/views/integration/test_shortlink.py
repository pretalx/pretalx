# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scopes_disabled

from pretalx.submission.models import SubmissionStates
from tests.factories import (
    EventFactory,
    SpeakerFactory,
    SubmissionFactory,
    TalkSlotFactory,
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_shortlink_view_submission_orga(client, event):
    """Organisers are redirected to the orga submission page."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(f"/redirect/{submission.code}")

    assert response.status_code == 302
    assert response.url == submission.orga_urls.base


def test_shortlink_view_submission_public(client, published_talk_slot):
    """Users with public view permission see the public submission URL."""
    submission = published_talk_slot.submission
    user = UserFactory()
    client.force_login(user)

    response = client.get(f"/redirect/{submission.code}")

    assert response.status_code == 302
    assert response.url == submission.urls.public


def test_shortlink_view_speaker_orga(client, event):
    """Organisers are redirected to the orga speaker page for a speaker code."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(f"/redirect/{speaker.code}")

    assert response.status_code == 302
    assert response.url == speaker.orga_urls.base


def test_shortlink_view_speaker_own_profile(client, event):
    """Speakers looking up their own code get redirected to their event page."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
    client.force_login(speaker.user)

    response = client.get(f"/redirect/{speaker.code}")

    assert response.status_code == 302
    assert response.url == event.urls.user


def test_shortlink_view_unknown_code(client, event):
    """Unknown codes raise 404."""
    with scopes_disabled():
        user = make_orga_user(event)
    client.force_login(user)

    response = client.get("/redirect/NONEXISTENT")

    assert response.status_code == 404


def test_shortlink_view_anonymous_no_access(client, event):
    """Anonymous users without any matching permissions get 404."""
    with scopes_disabled():
        submission = SubmissionFactory(event=event)

    response = client.get(f"/redirect/{submission.code}")

    assert response.status_code == 404


def test_shortlink_view_speaker_no_access(client, event):
    """A logged-in user without orga/admin/self permissions for a speaker code
    gets 404 when the event has no published schedule."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        other_user = UserFactory()
    client.force_login(other_user)

    response = client.get(f"/redirect/{speaker.code}")

    assert response.status_code == 404


def test_shortlink_view_speaker_admin(client, event):
    """Admins looking up a speaker code get redirected to the user admin page."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        admin = UserFactory(is_administrator=True)
    client.force_login(admin)

    response = client.get(f"/redirect/{speaker.code}")

    assert response.status_code == 302
    assert response.url == speaker.user.orga_urls.admin


def test_shortlink_view_speaker_public(client, event):
    """Public users can follow a speaker code to the public speaker page."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        slot = TalkSlotFactory(submission=submission, is_visible=True)
        slot.schedule.freeze("v1", notify_speakers=False)
    user = UserFactory()
    client.force_login(user)

    response = client.get(f"/redirect/{speaker.code}")

    assert response.status_code == 302
    assert response.url == speaker.urls.public


def test_shortlink_view_user_code_admin(client):
    """Admin users can look up a User by code and get redirected to admin."""
    with scopes_disabled():
        target_user = UserFactory()
        admin = UserFactory(is_administrator=True)
    client.force_login(admin)

    response = client.get(f"/redirect/{target_user.code}")

    assert response.status_code == 302
    assert response.url == target_user.orga_urls.admin


def test_shortlink_view_user_code_non_admin_returns_404(client):
    """Non-admin users looking up a User code get 404."""
    with scopes_disabled():
        target_user = UserFactory()
        regular_user = UserFactory()
    client.force_login(regular_user)

    response = client.get(f"/redirect/{target_user.code}")

    assert response.status_code == 404


def test_shortlink_view_speaker_public_skips_private_event(client):
    """When a speaker code matches profiles in multiple events,
    private events are skipped in the public-view loop."""
    with scopes_disabled():
        private_event = EventFactory(is_public=False)
        public_event = EventFactory(is_public=True)

        user_obj = UserFactory()
        public_speaker = SpeakerFactory(event=public_event, user=user_obj)
        SpeakerFactory(event=private_event, user=user_obj, code=public_speaker.code)

        submission = SubmissionFactory(
            event=public_event, state=SubmissionStates.CONFIRMED
        )
        submission.speakers.add(public_speaker)
        slot = TalkSlotFactory(submission=submission, is_visible=True)
        slot.schedule.freeze("v1", notify_speakers=False)

    viewer = UserFactory()
    client.force_login(viewer)

    response = client.get(f"/redirect/{public_speaker.code}")

    assert response.status_code == 302
    assert response.url == public_speaker.urls.public
