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


def test_shortlink_view_orga_targets(client, event):
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        speaker = SpeakerFactory(event=event)
        managed_speaker = SpeakerFactory(event=event, user=None)
        user = make_orga_user(event, can_change_submissions=True)

    assert client.get(f"/redirect/{submission.code}").status_code == 404

    client.force_login(user)

    response = client.get(f"/redirect/{submission.code}")
    assert response.status_code == 302
    assert response.url == submission.orga_urls.base

    response = client.get(f"/redirect/{speaker.code}")
    assert response.status_code == 302
    assert response.url == speaker.orga_urls.base

    response = client.get(f"/redirect/{managed_speaker.code}")
    assert response.status_code == 302
    assert response.url == managed_speaker.orga_urls.base

    assert client.get("/redirect/NONEXISTENT").status_code == 404


def test_shortlink_view_submission_public(client, published_talk_slot):
    submission = published_talk_slot.submission
    user = UserFactory()
    client.force_login(user)

    response = client.get(f"/redirect/{submission.code}")

    assert response.status_code == 302
    assert response.url == submission.urls.public


def test_shortlink_view_speaker_own_profile(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
    client.force_login(speaker.user)

    response = client.get(f"/redirect/{speaker.code}")

    assert response.status_code == 302
    assert response.url == event.urls.user


def test_shortlink_view_regular_user_has_no_access_to_speaker_or_user_codes(
    client, event
):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        target_user = UserFactory()
        regular_user = UserFactory()
    client.force_login(regular_user)

    assert client.get(f"/redirect/{speaker.code}").status_code == 404
    assert client.get(f"/redirect/{target_user.code}").status_code == 404


def test_shortlink_view_admin_targets(client, event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        target_user = UserFactory()
        admin = UserFactory(is_administrator=True)
    client.force_login(admin)

    response = client.get(f"/redirect/{speaker.code}")
    assert response.status_code == 302
    assert response.url == speaker.user.orga_urls.admin

    response = client.get(f"/redirect/{target_user.code}")
    assert response.status_code == 302
    assert response.url == target_user.orga_urls.admin


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
