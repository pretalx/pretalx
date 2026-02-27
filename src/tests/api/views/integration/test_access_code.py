import json

import pytest
from django_scopes import scopes_disabled

from tests.factories import (
    SubmissionFactory,
    SubmissionTypeFactory,
    SubmitterAccessCodeFactory,
    TrackFactory,
)

pytestmark = pytest.mark.integration


@pytest.mark.django_db
@pytest.mark.parametrize("is_public", (True, False))
def test_access_code_list_requires_auth(client, event, is_public):
    """Unauthenticated access code list returns 401 regardless of event visibility."""
    event.is_public = is_public
    event.save()
    with scopes_disabled():
        SubmitterAccessCodeFactory(event=event)

    response = client.get(event.api_urls.access_codes, follow=True)

    assert response.status_code == 401


@pytest.mark.django_db
def test_access_code_list_with_orga_read_token(client, event, orga_read_token):
    """Organiser with read token can list access codes."""
    with scopes_disabled():
        code = SubmitterAccessCodeFactory(event=event)

    response = client.get(
        event.api_urls.access_codes,
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["results"][0]["code"] == code.code


@pytest.mark.django_db
@pytest.mark.parametrize("item_count", (1, 3))
def test_access_code_list_query_count(
    client, event, orga_read_token, item_count, django_assert_num_queries
):
    """Query count for access code list is constant regardless of item count."""
    with scopes_disabled():
        for _ in range(item_count):
            SubmitterAccessCodeFactory(event=event)

    with django_assert_num_queries(13):
        response = client.get(
            event.api_urls.access_codes,
            follow=True,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    assert response.status_code == 200
    assert response.json()["count"] == item_count


@pytest.mark.django_db
def test_access_code_detail_with_orga_read_token(client, event, orga_read_token):
    """Organiser can retrieve a single access code with all fields."""
    with scopes_disabled():
        code = SubmitterAccessCodeFactory(
            event=event, maximum_uses=5, internal_notes="Test note"
        )

    response = client.get(
        event.api_urls.access_codes + f"{code.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == code.pk
    assert data["code"] == code.code
    assert data["maximum_uses"] == 5
    assert data["redeemed"] == 0
    assert data["internal_notes"] == "Test note"


@pytest.mark.django_db
def test_access_code_create_with_write_token(client, event, orga_write_token):
    """POST with a write token creates a new access code."""
    response = client.post(
        event.api_urls.access_codes,
        follow=True,
        data=json.dumps({"code": "TESTCODE123", "maximum_uses": 10}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["code"] == "TESTCODE123"
    assert data["maximum_uses"] == 10
    with scopes_disabled():
        code = event.submitter_access_codes.get(code="TESTCODE123")
        assert code.maximum_uses == 10
        assert (
            code.logged_actions()
            .filter(action_type="pretalx.access_code.create")
            .exists()
        )


@pytest.mark.django_db
def test_access_code_create_rejected_with_read_token(client, event, orga_read_token):
    """POST with a read-only token returns 403."""
    response = client.post(
        event.api_urls.access_codes,
        follow=True,
        data=json.dumps({"code": "FORBIDDEN"}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        assert not event.submitter_access_codes.filter(code="FORBIDDEN").exists()


@pytest.mark.django_db
def test_access_code_create_with_track(client, event, orga_write_token):
    """Access code can be created with a track restriction (v1 singular field)."""
    with scopes_disabled():
        track = TrackFactory(event=event)

    response = client.post(
        event.api_urls.access_codes,
        follow=True,
        data=json.dumps({"code": "TRACKED", "track": track.pk}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201
    with scopes_disabled():
        code = event.submitter_access_codes.get(code="TRACKED")
        assert list(code.tracks.all()) == [track]


@pytest.mark.django_db
def test_access_code_create_rejects_track_from_other_event(
    client, event, orga_write_token, other_event
):
    """Creating an access code with a track from a different event returns 400."""
    with scopes_disabled():
        other_track = TrackFactory(event=other_event)

    response = client.post(
        event.api_urls.access_codes,
        follow=True,
        data=json.dumps({"code": "BADTRACK", "track": other_track.pk}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_access_code_update_with_write_token(client, event, orga_write_token):
    """PATCH with a write token updates the access code."""
    with scopes_disabled():
        code = SubmitterAccessCodeFactory(event=event, maximum_uses=1)

    response = client.patch(
        event.api_urls.access_codes + f"{code.pk}/",
        follow=True,
        data=json.dumps({"maximum_uses": 99}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200
    with scopes_disabled():
        code.refresh_from_db()
        assert code.maximum_uses == 99
        assert (
            code.logged_actions()
            .filter(action_type="pretalx.access_code.update")
            .exists()
        )


@pytest.mark.django_db
def test_access_code_update_rejected_with_read_token(client, event, orga_read_token):
    """PATCH with a read-only token returns 403."""
    with scopes_disabled():
        code = SubmitterAccessCodeFactory(event=event, maximum_uses=1)

    response = client.patch(
        event.api_urls.access_codes + f"{code.pk}/",
        follow=True,
        data=json.dumps({"maximum_uses": 99}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        code.refresh_from_db()
        assert code.maximum_uses == 1


@pytest.mark.django_db
def test_access_code_delete_with_write_token(client, event, orga_write_token):
    """DELETE with a write token removes the access code."""
    with scopes_disabled():
        code = SubmitterAccessCodeFactory(event=event)
        code_pk = code.pk

    response = client.delete(
        event.api_urls.access_codes + f"{code_pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 204
    with scopes_disabled():
        assert not event.submitter_access_codes.filter(pk=code_pk).exists()
        assert (
            event.logged_actions()
            .filter(action_type="pretalx.access_code.delete")
            .exists()
        )


@pytest.mark.django_db
def test_access_code_delete_rejected_with_read_token(client, event, orga_read_token):
    """DELETE with a read-only token returns 403."""
    with scopes_disabled():
        code = SubmitterAccessCodeFactory(event=event)

    response = client.delete(
        event.api_urls.access_codes + f"{code.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        assert event.submitter_access_codes.filter(pk=code.pk).exists()


@pytest.mark.django_db
def test_access_code_delete_used_code_returns_400(client, event, orga_write_token):
    """Deleting an access code that has been used by a submission returns 400."""
    with scopes_disabled():
        code = SubmitterAccessCodeFactory(event=event)
        SubmissionFactory(event=event, access_code=code)

    response = client.delete(
        event.api_urls.access_codes + f"{code.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 400
    with scopes_disabled():
        assert event.submitter_access_codes.filter(pk=code.pk).exists()


@pytest.mark.django_db
def test_access_code_list_rejects_legacy_version(client, event, orga_read_token):
    """GET with Pretalx-Version: LEGACY returns 400."""
    response = client.get(
        event.api_urls.access_codes,
        follow=True,
        headers={
            "Authorization": f"Token {orga_read_token.token}",
            "Pretalx-Version": "LEGACY",
        },
    )

    assert response.status_code == 400
    assert "not supported" in response.json()["detail"].lower()


@pytest.mark.django_db
def test_access_code_detail_v1_shows_singular_fields(client, event, orga_read_token):
    """V1 response uses singular track/submission_type fields."""
    with scopes_disabled():
        track = TrackFactory(event=event)
        sub_type = SubmissionTypeFactory(event=event)
        code = SubmitterAccessCodeFactory(event=event)
        code.tracks.add(track)
        code.submission_types.add(sub_type)

    response = client.get(
        event.api_urls.access_codes + f"{code.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "track" in data
    assert "submission_type" in data
    assert "tracks" not in data
    assert "submission_types" not in data
    assert data["track"] == track.pk
    assert data["submission_type"] == sub_type.pk


@pytest.mark.django_db
def test_access_code_detail_v1_returns_first_entry_only(client, event, orga_read_token):
    """V1 singular fields return only one item when multiple are associated."""
    with scopes_disabled():
        track1 = TrackFactory(event=event)
        track2 = TrackFactory(event=event)
        sub_type1 = SubmissionTypeFactory(event=event)
        sub_type2 = SubmissionTypeFactory(event=event)
        code = SubmitterAccessCodeFactory(event=event)
        code.tracks.add(track1, track2)
        code.submission_types.add(sub_type1, sub_type2)

    response = client.get(
        event.api_urls.access_codes + f"{code.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["track"] in (track1.pk, track2.pk)
    assert data["submission_type"] in (sub_type1.pk, sub_type2.pk)


@pytest.mark.django_db
def test_access_code_detail_v1_null_when_empty(client, event, orga_read_token):
    """V1 track/submission_type are null when no M2M entries exist."""
    with scopes_disabled():
        code = SubmitterAccessCodeFactory(event=event)

    response = client.get(
        event.api_urls.access_codes + f"{code.pk}/",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["track"] is None
    assert data["submission_type"] is None


@pytest.mark.django_db
def test_access_code_detail_v1_expand_track(client, event, orga_read_token):
    """V1 ?expand=track,submission_type returns expanded objects."""
    with scopes_disabled():
        track = TrackFactory(event=event)
        sub_type = SubmissionTypeFactory(event=event)
        code = SubmitterAccessCodeFactory(event=event)
        code.tracks.add(track)
        code.submission_types.add(sub_type)

    response = client.get(
        event.api_urls.access_codes + f"{code.pk}/?expand=track,submission_type",
        follow=True,
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["track"], dict)
    assert isinstance(data["submission_type"], dict)


@pytest.mark.django_db
def test_access_code_create_v1_with_submission_type(client, event, orga_write_token):
    """V1 POST with singular track and submission_type sets both M2M relations."""
    with scopes_disabled():
        track = TrackFactory(event=event)
        sub_type = SubmissionTypeFactory(event=event)

    response = client.post(
        event.api_urls.access_codes,
        follow=True,
        data=json.dumps(
            {"code": "FULLV1", "track": track.pk, "submission_type": sub_type.pk}
        ),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 201
    with scopes_disabled():
        code = event.submitter_access_codes.get(code="FULLV1")
        assert list(code.tracks.all()) == [track]
        assert list(code.submission_types.all()) == [sub_type]


@pytest.mark.django_db
def test_access_code_update_v1_track(client, event, orga_write_token):
    """V1 PATCH with singular track and submission_type sets the M2M relations."""
    with scopes_disabled():
        code = SubmitterAccessCodeFactory(event=event)
        track = TrackFactory(event=event)
        sub_type = SubmissionTypeFactory(event=event)

    response = client.patch(
        event.api_urls.access_codes + f"{code.pk}/",
        follow=True,
        data=json.dumps({"track": track.pk, "submission_type": sub_type.pk}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200
    with scopes_disabled():
        code.refresh_from_db()
        assert list(code.tracks.all()) == [track]
        assert list(code.submission_types.all()) == [sub_type]


@pytest.mark.django_db
def test_access_code_update_v1_clear_track(client, event, orga_write_token):
    """V1 PATCH with track: null and submission_type: null clears M2M relations."""
    with scopes_disabled():
        track = TrackFactory(event=event)
        sub_type = SubmissionTypeFactory(event=event)
        code = SubmitterAccessCodeFactory(event=event)
        code.tracks.add(track)
        code.submission_types.add(sub_type)

    response = client.patch(
        event.api_urls.access_codes + f"{code.pk}/",
        follow=True,
        data=json.dumps({"track": None, "submission_type": None}),
        content_type="application/json",
        headers={"Authorization": f"Token {orga_write_token.token}"},
    )

    assert response.status_code == 200
    with scopes_disabled():
        code.refresh_from_db()
        assert code.tracks.count() == 0
        assert code.submission_types.count() == 0


@pytest.mark.django_db
def test_access_code_detail_dev_preview_shows_plural_fields(
    client, event, orga_read_token
):
    """DEV_PREVIEW response uses plural tracks/submission_types fields."""
    with scopes_disabled():
        track = TrackFactory(event=event)
        sub_type = SubmissionTypeFactory(event=event)
        code = SubmitterAccessCodeFactory(event=event)
        code.tracks.add(track)
        code.submission_types.add(sub_type)

    response = client.get(
        event.api_urls.access_codes + f"{code.pk}/",
        follow=True,
        headers={
            "Authorization": f"Token {orga_read_token.token}",
            "Pretalx-Version": "v-next",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "tracks" in data
    assert "submission_types" in data
    assert "track" not in data
    assert "submission_type" not in data
    assert data["tracks"] == [track.pk]
    assert data["submission_types"] == [sub_type.pk]


@pytest.mark.django_db
def test_access_code_dev_preview_expand_tracks(client, event, orga_read_token):
    """DEV_PREVIEW ?expand=tracks,submission_types returns expanded objects."""
    with scopes_disabled():
        track = TrackFactory(event=event)
        sub_type = SubmissionTypeFactory(event=event)
        code = SubmitterAccessCodeFactory(event=event)
        code.tracks.add(track)
        code.submission_types.add(sub_type)

    response = client.get(
        event.api_urls.access_codes + f"{code.pk}/?expand=tracks,submission_types",
        follow=True,
        headers={
            "Authorization": f"Token {orga_read_token.token}",
            "Pretalx-Version": "v-next",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["tracks"]) == 1
    assert data["tracks"][0]["name"]["en"] == str(track.name)
    assert len(data["submission_types"]) == 1
    assert data["submission_types"][0]["name"]["en"] == str(sub_type.name)
