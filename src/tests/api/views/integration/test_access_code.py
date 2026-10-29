# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scopes_disabled

from tests.factories import (
    EventFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    SubmitterAccessCodeFactory,
    TrackFactory,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_access_code_list_requires_auth(client):
    event = EventFactory()
    with scopes_disabled():
        SubmitterAccessCodeFactory(event=event)

    response = client.get(event.api_urls.access_codes, follow=True)

    assert response.status_code == 401


@pytest.mark.parametrize("item_count", (1, 3))
def test_access_code_list_with_orga_read_token(
    client, event, orga_read_token, item_count, django_assert_num_queries
):
    with scopes_disabled():
        codes = SubmitterAccessCodeFactory.create_batch(item_count, event=event)

    with django_assert_num_queries(12):
        response = client.get(
            event.api_urls.access_codes,
            follow=True,
            headers={"Authorization": f"Token {orga_read_token.token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == item_count
    assert {r["code"] for r in data["results"]} == {c.code for c in codes}


@pytest.mark.parametrize(
    "extra_headers",
    ({}, {"Pretalx-Version": "v-next"}),
    ids=["default-v2", "dev-preview"],
)
def test_access_code_detail_with_orga_read_token(
    client, event, orga_read_token, extra_headers
):
    with scopes_disabled():
        track = TrackFactory(event=event)
        sub_type = SubmissionTypeFactory(event=event)
        code = SubmitterAccessCodeFactory(
            event=event, maximum_uses=5, internal_notes="Test note"
        )
        code.tracks.add(track)
        code.submission_types.add(sub_type)
    headers = {"Authorization": f"Token {orga_read_token.token}", **extra_headers}

    response = client.get(
        event.api_urls.access_codes + f"{code.pk}/", follow=True, headers=headers
    )
    expanded = client.get(
        event.api_urls.access_codes + f"{code.pk}/?expand=tracks,submission_types",
        follow=True,
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": code.pk,
        "code": code.code,
        "tracks": [track.pk],
        "submission_types": [sub_type.pk],
        "valid_until": None,
        "maximum_uses": 5,
        "redeemed": 0,
        "internal_notes": "Test note",
    }
    assert expanded.status_code == 200
    data = expanded.json()
    assert [t["name"]["en"] for t in data["tracks"]] == [str(track.name)]
    assert [t["name"]["en"] for t in data["submission_types"]] == [str(sub_type.name)]


def test_access_code_create_with_write_token(client, event, orga_write_token):
    with scopes_disabled():
        track = TrackFactory(event=event)
        other_track = TrackFactory(event=EventFactory())
    headers = {"Authorization": f"Token {orga_write_token.token}"}

    response = client.post(
        event.api_urls.access_codes,
        follow=True,
        data={"code": "TESTCODE123", "maximum_uses": 10, "tracks": [track.pk]},
        content_type="application/json",
        headers=headers,
    )
    rejected = client.post(
        event.api_urls.access_codes,
        follow=True,
        data={"code": "BADTRACK", "tracks": [other_track.pk]},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["code"] == "TESTCODE123"
    assert data["maximum_uses"] == 10
    with scopes_disabled():
        code = event.submitter_access_codes.get(code="TESTCODE123")
        assert code.maximum_uses == 10
        assert list(code.tracks.all()) == [track]
        assert (
            code.logged_actions()
            .filter(action_type="pretalx.access_code.create")
            .exists()
        )
    assert rejected.status_code == 400
    assert rejected.json() == {
        "tracks": [f'Invalid pk "{other_track.pk}" - object does not exist.']
    }
    with scopes_disabled():
        assert not event.submitter_access_codes.filter(code="BADTRACK").exists()


def test_access_code_create_rejected_with_read_token(client, event, orga_read_token):
    response = client.post(
        event.api_urls.access_codes,
        follow=True,
        data={"code": "FORBIDDEN"},
        content_type="application/json",
        headers={"Authorization": f"Token {orga_read_token.token}"},
    )

    assert response.status_code == 403
    with scopes_disabled():
        assert not event.submitter_access_codes.filter(code="FORBIDDEN").exists()


def test_access_code_update_and_delete_with_write_token(
    client, event, orga_write_token
):
    with scopes_disabled():
        code = SubmitterAccessCodeFactory(event=event, maximum_uses=1)
    url = event.api_urls.access_codes + f"{code.pk}/"
    headers = {"Authorization": f"Token {orga_write_token.token}"}

    response = client.patch(
        url,
        follow=True,
        data={"maximum_uses": 99},
        content_type="application/json",
        headers=headers,
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

    response = client.delete(url, follow=True, headers=headers)

    assert response.status_code == 204
    with scopes_disabled():
        assert not event.submitter_access_codes.filter(pk=code.pk).exists()
        assert (
            event.logged_actions()
            .filter(action_type="pretalx.access_code.delete")
            .exists()
        )


def test_access_code_delete_used_code_returns_400(client, event, orga_write_token):
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


def test_access_code_detail_v1_shows_singular_fields(client, event, orga_read_token):
    with scopes_disabled():
        track1 = TrackFactory(event=event)
        track2 = TrackFactory(event=event)
        sub_type1 = SubmissionTypeFactory(event=event)
        sub_type2 = SubmissionTypeFactory(event=event)
        code = SubmitterAccessCodeFactory(event=event, maximum_uses=5)
        code.tracks.add(track1, track2)
        code.submission_types.add(sub_type1, sub_type2)
        empty_code = SubmitterAccessCodeFactory(event=event)
    headers = {
        "Authorization": f"Token {orga_read_token.token}",
        "Pretalx-Version": "v1",
    }

    response = client.get(
        event.api_urls.access_codes + f"{code.pk}/", follow=True, headers=headers
    )
    expanded = client.get(
        event.api_urls.access_codes + f"{code.pk}/?expand=track,submission_type",
        follow=True,
        headers=headers,
    )
    empty = client.get(
        event.api_urls.access_codes + f"{empty_code.pk}/", follow=True, headers=headers
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": code.pk,
        "code": code.code,
        "track": track1.pk,
        "submission_type": sub_type1.pk,
        "valid_until": None,
        "maximum_uses": 5,
        "redeemed": 0,
        "internal_notes": None,
    }
    assert expanded.status_code == 200
    assert expanded.json()["track"]["id"] == track1.pk
    assert expanded.json()["submission_type"]["id"] == sub_type1.pk
    assert empty.status_code == 200
    assert empty.json()["track"] is None
    assert empty.json()["submission_type"] is None


def test_access_code_create_and_update_v1_track_and_submission_type(
    client, event, orga_write_token
):
    with scopes_disabled():
        track = TrackFactory(event=event)
        sub_type = SubmissionTypeFactory(event=event)
    headers = {
        "Authorization": f"Token {orga_write_token.token}",
        "Pretalx-Version": "v1",
    }

    response = client.post(
        event.api_urls.access_codes,
        follow=True,
        data={"code": "FULLV1", "track": track.pk, "submission_type": sub_type.pk},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 201
    with scopes_disabled():
        code = event.submitter_access_codes.get(code="FULLV1")
        assert list(code.tracks.all()) == [track]
        assert list(code.submission_types.all()) == [sub_type]
    url = event.api_urls.access_codes + f"{code.pk}/"

    response = client.patch(
        url,
        follow=True,
        data={"track": None, "submission_type": None},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert list(code.tracks.all()) == []
        assert list(code.submission_types.all()) == []

    response = client.patch(
        url,
        follow=True,
        data={"track": track.pk, "submission_type": sub_type.pk},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200
    with scopes_disabled():
        assert list(code.tracks.all()) == [track]
        assert list(code.submission_types.all()) == [sub_type]
