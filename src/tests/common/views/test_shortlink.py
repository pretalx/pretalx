# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scope

from pretalx.person.models import SpeakerProfile


@pytest.mark.django_db
def test_shortlink_submission_orga_access(orga_client, submission, event):
    with scope(event=event):
        response = orga_client.get(f"/redirect/{submission.code}")
        assert response.status_code == 302
        assert response.url == submission.orga_urls.base


@pytest.mark.django_db
def test_shortlink_submission_public_access(client, slot):
    confirmed_submission = slot.submission
    response = client.get(f"/redirect/{confirmed_submission.code}")
    assert response.status_code == 302
    assert response.url == confirmed_submission.urls.public


@pytest.mark.django_db
def test_shortlink_submission_no_access(client, submission, event):
    with scope(event=event):
        response = client.get(f"/redirect/{submission.code}")
        assert response.status_code == 404


@pytest.mark.django_db
def test_shortlink_user_admin_access(client, speaker, event):
    from pretalx.person.models import User

    admin_user = User.objects.create_user("admin@example.com", is_administrator=True)
    client.force_login(admin_user)
    response = client.get(f"/redirect/{speaker.code}")
    assert response.status_code == 302
    assert response.url == speaker.orga_urls.admin


@pytest.mark.django_db
def test_shortlink_user_orga_access_to_profile(orga_client, speaker, event):
    with scope(event=event):
        profile = SpeakerProfile.objects.get(user=speaker, event=event)
        response = orga_client.get(f"/redirect/{speaker.code}")
        assert response.status_code == 302
        assert response.url == profile.orga_urls.base


@pytest.mark.django_db
def test_shortlink_user_self_access(client, speaker, event):
    client.force_login(speaker)
    with scope(event=event):
        response = client.get(f"/redirect/{speaker.code}")
        assert response.status_code == 302
        assert response.url == event.urls.user


@pytest.mark.django_db
def test_shortlink_user_public_profile_access(client, slot):
    speaker = slot.submission.speakers.first()
    event = slot.submission.event
    with scope(event=event):
        profile = SpeakerProfile.objects.get(user=speaker, event=event)
        response = client.get(f"/redirect/{speaker.code}")
        assert response.status_code == 302
        assert response.url == profile.urls.public


@pytest.mark.django_db
def test_shortlink_user_no_profiles(client, user):
    response = client.get(f"/redirect/{user.code}")
    assert response.status_code == 404


@pytest.mark.django_db
def test_shortlink_user_no_access(client, other_speaker, event):
    with scope(event=event):
        response = client.get(f"/redirect/{other_speaker.code}")
        assert response.status_code == 404


@pytest.mark.django_db
def test_shortlink_nonexistent_code(client):
    response = client.get("/redirect/NONEXISTENT")
    assert response.status_code == 404


@pytest.mark.django_db
def test_shortlink_empty_code(client):
    response = client.get("/redirect/")
    assert response.status_code == 400


@pytest.mark.django_db
def test_shortlink_multiple_profiles_latest_first(
    orga_client, speaker, event, other_event
):
    with scope(event=other_event):
        SpeakerProfile.objects.get_or_create(user=speaker, event=other_event)

    response = orga_client.get(f"/redirect/{speaker.code}")
    assert response.status_code == 302
    assert "/orga/event/" in response.url
    assert f"/speakers/{speaker.code}/" in response.url


@pytest.mark.django_db
def test_shortlink_user_multiple_events_no_orga_access(
    client, speaker, event, other_event
):
    client.force_login(speaker)
    with scope(event=other_event):
        SpeakerProfile.objects.get_or_create(user=speaker, event=other_event)

    response = client.get(f"/redirect/{speaker.code}")
    assert response.status_code == 302
    assert response.url == other_event.urls.user
