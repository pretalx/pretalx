# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest

from pretalx.api.serializers.access_code import (
    SubmitterAccessCodeSerializer,
    V1SubmitterAccessCodeSerializer,
)
from tests.factories import (
    EventFactory,
    SubmissionTypeFactory,
    SubmitterAccessCodeFactory,
    TrackFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_submitter_access_code_serializer_data():
    access_code = SubmitterAccessCodeFactory()
    track = TrackFactory(event=access_code.event)
    sub_type = SubmissionTypeFactory(event=access_code.event)
    access_code.tracks.add(track)
    access_code.submission_types.add(sub_type)

    data = SubmitterAccessCodeSerializer(
        access_code, context={"event": access_code.event}
    ).data
    assert data == {
        "id": access_code.pk,
        "code": access_code.code,
        "tracks": [track.pk],
        "submission_types": [sub_type.pk],
        "valid_until": None,
        "maximum_uses": access_code.maximum_uses,
        "redeemed": 0,
        "internal_notes": None,
    }


def test_submitter_access_code_serializer_scopes_querysets_to_event(rf):
    event = EventFactory()
    TrackFactory(event=event)
    SubmissionTypeFactory(event=event)
    other_event = EventFactory()
    TrackFactory(event=other_event)
    SubmissionTypeFactory(event=other_event)

    request = rf.get("/")
    request.event = event
    request.query_params = request.GET
    serializer = SubmitterAccessCodeSerializer(context={"request": request})
    track_qs = serializer.fields["tracks"].child_relation.queryset
    type_qs = serializer.fields["submission_types"].child_relation.queryset
    assert set(track_qs) == set(event.tracks.all())
    assert set(type_qs) == set(event.submission_types.all())


def test_submitter_access_code_serializer_create_sets_event(rf):
    event = EventFactory()
    request = rf.get("/")
    request.event = event
    request.query_params = request.GET
    serializer = SubmitterAccessCodeSerializer(context={"request": request})
    instance = serializer.create({"code": "testcreatecode"})

    assert instance.pk is not None
    assert instance.event == event
    assert instance.code == "testcreatecode"


def test_v1_access_code_serializer_scopes_querysets_to_event(rf):
    event = EventFactory()
    TrackFactory(event=event)
    SubmissionTypeFactory(event=event)
    other_event = EventFactory()
    TrackFactory(event=other_event)
    SubmissionTypeFactory(event=other_event)

    request = rf.get("/")
    request.event = event
    serializer = V1SubmitterAccessCodeSerializer(context={"request": request})
    track_qs = serializer.fields["track"].queryset
    type_qs = serializer.fields["submission_type"].queryset
    assert set(track_qs) == set(event.tracks.all())
    assert set(type_qs) == set(event.submission_types.all())


@pytest.mark.parametrize(
    ("field_name", "m2m_attr", "factory"),
    (
        ("track", "tracks", TrackFactory),
        ("submission_type", "submission_types", SubmissionTypeFactory),
    ),
)
def test_v1_access_code_serializer_to_representation_expanded(
    rf, field_name, m2m_attr, factory
):
    access_code = SubmitterAccessCodeFactory()
    related = factory(event=access_code.event)
    getattr(access_code, m2m_attr).add(related)

    request = rf.get("/", {"expand": field_name})
    request.event = access_code.event
    request.query_params = request.GET
    data = V1SubmitterAccessCodeSerializer(
        access_code, context={"request": request}
    ).data

    assert isinstance(data[field_name], dict)
    assert data[field_name]["id"] == related.pk
    assert data[field_name]["name"]["en"] == str(related.name)


def test_v1_access_code_serializer_to_representation_shows_first_only():
    access_code = SubmitterAccessCodeFactory()
    track1 = TrackFactory(event=access_code.event)
    track2 = TrackFactory(event=access_code.event)
    access_code.tracks.add(track1, track2)

    data = V1SubmitterAccessCodeSerializer(access_code).data

    assert data["track"] in (track1.pk, track2.pk)


def test_v1_access_code_serializer_create_with_track_and_type(rf):
    event = EventFactory()
    track = TrackFactory(event=event)
    sub_type = SubmissionTypeFactory(event=event)
    request = rf.get("/")
    request.event = event

    serializer = V1SubmitterAccessCodeSerializer(context={"request": request})
    instance = serializer.create(
        {"code": "v1create", "track": track, "submission_type": sub_type}
    )
    assert list(instance.tracks.all()) == [track]
    assert list(instance.submission_types.all()) == [sub_type]


def test_v1_access_code_serializer_create_without_track_or_type(rf):
    event = EventFactory()
    request = rf.get("/")
    request.event = event

    serializer = V1SubmitterAccessCodeSerializer(context={"request": request})
    instance = serializer.create({"code": "v1notype"})
    assert instance.tracks.count() == 0
    assert instance.submission_types.count() == 0


@pytest.mark.parametrize(
    ("field_name", "m2m_attr", "factory"),
    (
        ("track", "tracks", TrackFactory),
        ("submission_type", "submission_types", SubmissionTypeFactory),
    ),
)
def test_v1_access_code_serializer_update_sets_relation(
    rf, field_name, m2m_attr, factory
):
    access_code = SubmitterAccessCodeFactory()
    related = factory(event=access_code.event)
    request = rf.get("/")
    request.event = access_code.event

    serializer = V1SubmitterAccessCodeSerializer(context={"request": request})
    serializer.initial_data = {field_name: related.pk}
    updated = serializer.update(access_code, {field_name: related})
    assert list(getattr(updated, m2m_attr).all()) == [related]


@pytest.mark.parametrize(
    ("field_name", "m2m_attr", "factory"),
    (
        ("track", "tracks", TrackFactory),
        ("submission_type", "submission_types", SubmissionTypeFactory),
    ),
)
def test_v1_access_code_serializer_update_clears_relation_when_null_in_initial_data(
    rf, field_name, m2m_attr, factory
):
    access_code = SubmitterAccessCodeFactory()
    related = factory(event=access_code.event)
    getattr(access_code, m2m_attr).add(related)

    request = rf.get("/")
    request.event = access_code.event
    serializer = V1SubmitterAccessCodeSerializer(context={"request": request})
    serializer.initial_data = {field_name: None}
    updated = serializer.update(access_code, {})
    assert getattr(updated, m2m_attr).count() == 0


def test_v1_access_code_serializer_update_keeps_track_when_not_in_data(rf):
    access_code = SubmitterAccessCodeFactory()
    track = TrackFactory(event=access_code.event)
    access_code.tracks.add(track)

    request = rf.get("/")
    request.event = access_code.event
    serializer = V1SubmitterAccessCodeSerializer(context={"request": request})
    serializer.initial_data = {}
    updated = serializer.update(access_code, {})
    assert list(updated.tracks.all()) == [track]
