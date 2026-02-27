import json

import pytest
from django.core.files.base import ContentFile
from django_scopes import scopes_disabled

from pretalx.api.versions import LEGACY
from tests.factories import (
    SpeakerInformationFactory,
    SubmissionTypeFactory,
    TrackFactory,
)

pytestmark = pytest.mark.integration


@pytest.mark.django_db
@pytest.mark.parametrize("is_public", (True, False))
def test_speaker_information_list_requires_auth(client, event, is_public):
    """Speaker information list returns 401 for unauthenticated requests,
    regardless of whether the event is public."""
    event.is_public = is_public
    event.save()

    response = client.get(event.api_urls.speaker_information, follow=True)

    assert response.status_code == 401


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_speaker_information_list_query_count(
    client, event, orga_token, item_count, django_assert_num_queries
):
    """Query count for speaker information list is constant regardless of item count."""
    with scopes_disabled():
        for _ in range(item_count):
            SpeakerInformationFactory(event=event)

    with django_assert_num_queries(13):
        response = client.get(
            event.api_urls.speaker_information,
            follow=True,
            headers={"Authorization": f"Token {orga_token.token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == item_count


@pytest.mark.django_db
def test_speaker_information_detail_accessible_with_token(client, event, orga_token):
    """Authenticated orga can retrieve a single speaker information entry."""
    with scopes_disabled():
        info = SpeakerInformationFactory(
            event=event, title="Important Info", text="Details here"
        )

    response = client.get(
        event.api_urls.speaker_information + f"{info.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"]["en"] == "Important Info"
    assert data["text"]["en"] == "Details here"


@pytest.mark.django_db
def test_speaker_information_legacy_api_not_supported(client, event, orga_token):
    """Requesting speaker information with legacy API version returns 400."""
    with scopes_disabled():
        info = SpeakerInformationFactory(event=event)

    response = client.get(
        event.api_urls.speaker_information + f"{info.pk}/",
        follow=True,
        headers={
            "Authorization": f"Token {orga_token.token}",
            "Pretalx-Version": LEGACY,
        },
    )

    assert response.status_code == 400
    assert "API version not supported." in response.content.decode()


@pytest.mark.django_db
def test_speaker_information_create_with_write_token(client, event, orga_write_token):
    """POST with a write token creates speaker information and logs the action."""
    response = client.post(
        event.api_urls.speaker_information,
        follow=True,
        data={
            "title": "New Info",
            "text": "New text content",
            "target_group": "accepted",
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201
    with scopes_disabled():
        info = event.information.get(title="New Info")
        assert info.text == "New text content"
        assert info.target_group == "accepted"
        assert (
            info.logged_actions()
            .filter(action_type="pretalx.speaker_information.create")
            .exists()
        )


@pytest.mark.django_db
def test_speaker_information_create_rejected_with_read_token(client, event, orga_token):
    """POST with a read-only token returns 403 and creates nothing."""
    response = client.post(
        event.api_urls.speaker_information,
        follow=True,
        data={
            "title": "Forbidden Info",
            "text": "Should not be created",
            "target_group": "accepted",
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        assert not event.information.filter(title="Forbidden Info").exists()


@pytest.mark.django_db
def test_speaker_information_update_with_write_token(client, event, orga_write_token):
    """PATCH with a write token updates speaker information and logs the action."""
    with scopes_disabled():
        info = SpeakerInformationFactory(event=event, title="Original Title")

    response = client.patch(
        event.api_urls.speaker_information + f"{info.pk}/",
        follow=True,
        data=json.dumps({"title": "Updated Title"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
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


@pytest.mark.django_db
def test_speaker_information_update_rejected_with_read_token(client, event, orga_token):
    """PATCH with a read-only token returns 403 and changes nothing."""
    with scopes_disabled():
        info = SpeakerInformationFactory(event=event, title="Unchanged")

    response = client.patch(
        event.api_urls.speaker_information + f"{info.pk}/",
        follow=True,
        data=json.dumps({"title": "Changed"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        info.refresh_from_db()
        assert info.title == "Unchanged"


@pytest.mark.django_db
def test_speaker_information_delete_with_write_token(client, event, orga_write_token):
    """DELETE with a write token removes the speaker information and logs the action."""
    with scopes_disabled():
        info = SpeakerInformationFactory(event=event)
        info_pk = info.pk

    response = client.delete(
        event.api_urls.speaker_information + f"{info_pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 204
    with scopes_disabled():
        assert not event.information.filter(pk=info_pk).exists()
        assert (
            event.logged_actions()
            .filter(action_type="pretalx.speaker_information.delete")
            .exists()
        )


@pytest.mark.django_db
def test_speaker_information_delete_rejected_with_read_token(client, event, orga_token):
    """DELETE with a read-only token returns 403 and keeps the entry."""
    with scopes_disabled():
        info = SpeakerInformationFactory(event=event)

    response = client.delete(
        event.api_urls.speaker_information + f"{info.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        assert event.information.filter(pk=info.pk).exists()


@pytest.mark.django_db
def test_speaker_information_expand_related_fields(client, event, orga_token):
    """The ?expand= parameter inlines related track and type objects."""
    with scopes_disabled():
        track = TrackFactory(event=event)
        sub_type = SubmissionTypeFactory(event=event)
        info = SpeakerInformationFactory(event=event, title="Expandable Info")
        info.limit_tracks.add(track)
        info.limit_types.add(sub_type)

    response = client.get(
        event.api_urls.speaker_information
        + f"{info.pk}/?expand=limit_tracks,limit_types",
        follow=True,
        headers={"Authorization": f"Token {orga_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"]["en"] == "Expandable Info"
    assert data["limit_tracks"][0]["name"]["en"] == track.name
    assert data["limit_types"][0]["name"]["en"] == sub_type.name


@pytest.mark.django_db
def test_speaker_information_create_with_resource(client, event, orga_write_token):
    """POST with a file upload attaches the resource to the speaker information."""
    upload_response = client.post(
        "/api/upload/",
        data={"file": ContentFile("Test PDF content", name="test.pdf")},
        headers={
            "Authorization": f"Token {orga_write_token.token}",
            "Content-Disposition": 'attachment; filename="test.pdf"',
            "Content-Type": "application/pdf",
        },
    )
    assert upload_response.status_code == 201
    file_id = upload_response.data["id"]

    response = client.post(
        event.api_urls.speaker_information,
        follow=True,
        data={
            "title": "Info with Resource",
            "text": "Has attached file",
            "target_group": "accepted",
            "resource": file_id,
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201
    with scopes_disabled():
        info = event.information.get(title="Info with Resource")
        assert info.resource is not None
        assert info.resource.name.endswith(".pdf")


@pytest.mark.django_db
def test_speaker_information_cross_event_track_rejected(
    client, event, orga_write_token, other_event
):
    """Assigning a track from a different event returns 400."""
    with scopes_disabled():
        other_track = TrackFactory(event=other_event)

    response = client.post(
        event.api_urls.speaker_information,
        follow=True,
        data={
            "title": "Cross-event Info",
            "text": "Should fail",
            "target_group": "accepted",
            "limit_tracks": [other_track.pk],
        },
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    assert "limit_tracks" in response.json()
    with scopes_disabled():
        assert not event.information.filter(title="Cross-event Info").exists()
