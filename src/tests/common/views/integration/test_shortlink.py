# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django_scopes import scopes_disabled

from pretalx.schedule.domain.release import freeze_schedule
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
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(f"/redirect/{submission.code}")

    assert response.status_code == 302
    assert response.url == submission.orga_urls.base


def test_shortlink_view_submission_public(client, published_talk_slot):
    submission = published_talk_slot.submission
    user = UserFactory()
    client.force_login(user)

    response = client.get(f"/redirect/{submission.code}")

    assert response.status_code == 302
    assert response.url == submission.urls.public


def test_shortlink_view_speaker_orga(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(f"/redirect/{speaker.code}")

    assert response.status_code == 302
    assert response.url == speaker.orga_urls.base


def test_shortlink_view_managed_speaker_orga(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event, user=None)
        user = make_orga_user(event, can_change_submissions=True)
    client.force_login(user)

    response = client.get(f"/redirect/{speaker.code}")

    assert response.status_code == 302
    assert response.url == speaker.orga_urls.base


def test_shortlink_view_speaker_own_profile(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
    client.force_login(speaker.user)

    response = client.get(f"/redirect/{speaker.code}")

    assert response.status_code == 302
    assert response.url == event.urls.user


def test_shortlink_view_unknown_code(client, event):
    with scopes_disabled():
        user = make_orga_user(event)
    client.force_login(user)

    response = client.get("/redirect/NONEXISTENT")

    assert response.status_code == 404


def test_shortlink_view_anonymous_no_access(client, event):
    with scopes_disabled():
        submission = SubmissionFactory(event=event)

    response = client.get(f"/redirect/{submission.code}")

    assert response.status_code == 404


def test_shortlink_view_speaker_no_access(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        other_user = UserFactory()
    client.force_login(other_user)

    response = client.get(f"/redirect/{speaker.code}")

    assert response.status_code == 404


def test_shortlink_view_speaker_admin(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        admin = UserFactory(is_administrator=True)
    client.force_login(admin)

    response = client.get(f"/redirect/{speaker.code}")

    assert response.status_code == 302
    assert response.url == speaker.user.orga_urls.admin


def test_shortlink_view_speaker_public(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        submission = SubmissionFactory(event=event, state=SubmissionStates.CONFIRMED)
        submission.speakers.add(speaker)
        slot = TalkSlotFactory(submission=submission, is_visible=True)
        freeze_schedule(slot.schedule, "v1", notify_speakers=False)
    user = UserFactory()
    client.force_login(user)

    response = client.get(f"/redirect/{speaker.code}")

    assert response.status_code == 302
    assert response.url == speaker.urls.public


def test_shortlink_view_user_code_admin(client):
    with scopes_disabled():
        target_user = UserFactory()
        admin = UserFactory(is_administrator=True)
    client.force_login(admin)

    response = client.get(f"/redirect/{target_user.code}")

    assert response.status_code == 302
    assert response.url == target_user.orga_urls.admin


def test_shortlink_view_user_code_non_admin_returns_404(client):
    with scopes_disabled():
        target_user = UserFactory()
        regular_user = UserFactory()
    client.force_login(regular_user)

    response = client.get(f"/redirect/{target_user.code}")

    assert response.status_code == 404


def test_shortlink_view_speaker_public_skips_private_event(client):
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
        freeze_schedule(slot.schedule, "v1", notify_speakers=False)

    viewer = UserFactory()
    client.force_login(viewer)

    response = client.get(f"/redirect/{public_speaker.code}")

    assert response.status_code == 302
    assert response.url == public_speaker.urls.public
