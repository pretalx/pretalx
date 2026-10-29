# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.core.files.base import ContentFile
from django_scopes import scopes_disabled

from tests.factories import (
    EventFactory,
    SpeakerInformationFactory,
    SubmissionTypeFactory,
    TrackFactory,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_speaker_information_list_requires_auth(client):
    event = EventFactory()

    response = client.get(event.api_urls.speaker_information, follow=True)

    assert response.status_code == 401


@pytest.mark.parametrize("item_count", (1, 3))
def test_speaker_information_list_query_count(
    client, event, orga_read_token, item_count, django_assert_num_queries
):
    with scopes_disabled():
        SpeakerInformationFactory.create_batch(item_count, event=event)

    with django_assert_num_queries(12):
        response = client.get(
            event.api_urls.speaker_information,
            follow=True,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == item_count


def test_speaker_information_detail_with_read_token(client, event, orga_read_token):
    with scopes_disabled():
        track = TrackFactory(event=event)
        sub_type = SubmissionTypeFactory(event=event)
        info = SpeakerInformationFactory(
            event=event, title="Important Info", text="Details here"
        )
        info.limit_tracks.add(track)
        info.limit_types.add(sub_type)
    url = event.api_urls.speaker_information + f"{info.pk}/"
    headers = {"Authorization": f"Token {orga_read_token.token}"}

    response = client.get(url, follow=True, headers=headers)
    expanded = client.get(
        url + "?expand=limit_tracks,limit_types", follow=True, headers=headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == {"en": "Important Info"}
    assert data["text"] == {"en": "Details here"}
    assert data["limit_tracks"] == [track.pk]
    assert data["limit_types"] == [sub_type.pk]
    assert expanded.status_code == 200
    data = expanded.json()
    assert [t["name"]["en"] for t in data["limit_tracks"]] == [track.name]
    assert [t["name"]["en"] for t in data["limit_types"]] == [sub_type.name]


def test_speaker_information_create_with_write_token(client, event, orga_write_token):
    with scopes_disabled():
        other_track = TrackFactory(event=EventFactory())
    headers = {"Authorization": f"Token {orga_write_token.token}"}
    upload_response = client.post(
        "/api/upload/",
        data={"file": ContentFile("Test PDF content", name="test.pdf")},
        headers={
            **headers,
            "Content-Disposition": 'attachment; filename="test.pdf"',
            "Content-Type": "application/pdf",
        },
    )
    assert upload_response.status_code == 201

    response = client.post(
        event.api_urls.speaker_information,
        follow=True,
        data={
            "title": "New Info",
            "text": "New text content",
            "target_group": "accepted",
            "resource": upload_response.data["id"],
        },
        content_type="application/json",
        headers=headers,
    )
    rejected = client.post(
        event.api_urls.speaker_information,
        follow=True,
        data={
            "title": "Cross-event Info",
            "text": "Should fail",
            "target_group": "accepted",
            "limit_tracks": [other_track.pk],
        },
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 201
    with scopes_disabled():
        info = event.information.get(title="New Info")
        assert info.text == "New text content"
        assert info.target_group == "accepted"
        assert info.resource.name.endswith(".pdf")
        assert (
            info.logged_actions()
            .filter(action_type="pretalx.speaker_information.create")
            .exists()
        )
    assert rejected.status_code == 400
    assert rejected.json() == {
        "limit_tracks": [f'Invalid pk "{other_track.pk}" - object does not exist.']
    }
    with scopes_disabled():
        assert not event.information.filter(title="Cross-event Info").exists()


def test_speaker_information_create_rejected_with_read_token(
    client, event, orga_read_token
):
    response = client.post(
        event.api_urls.speaker_information,
        follow=True,
        data={
            "title": "Forbidden Info",
            "text": "Should not be created",
            "target_group": "accepted",
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        assert not event.information.filter(title="Forbidden Info").exists()


def test_speaker_information_update_and_delete_with_write_token(
    client, event, orga_write_token
):
    with scopes_disabled():
        info = SpeakerInformationFactory(event=event, title="Original Title")
    url = event.api_urls.speaker_information + f"{info.pk}/"
    headers = {"Authorization": f"Token {orga_write_token.token}"}

    response = client.patch(
        url,
        follow=True,
        data={"title": "Updated Title"},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200
    with scopes_disabled():
        info.refresh_from_db()
        assert info.title == "Updated Title"
        assert (
            info.logged_actions()
            .filter(action_type="pretalx.speaker_information.update")
            .exists()
        )

    response = client.delete(url, follow=True, headers=headers)

    assert response.status_code == 204
    with scopes_disabled():
        assert not event.information.filter(pk=info.pk).exists()
        assert (
            event.logged_actions()
            .filter(action_type="pretalx.speaker_information.delete")
            .exists()
        )
