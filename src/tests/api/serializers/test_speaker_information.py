# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from pretalx.api.serializers.speaker_information import SpeakerInformationSerializer
from tests.factories import (
    EventFactory,
    SpeakerInformationFactory,
    SubmissionTypeFactory,
    TrackFactory,
)
from tests.utils import make_api_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_speaker_information_serializer_init_sets_track_queryset_from_event():
    """When initialized with an event, limit_tracks queryset is scoped to that event."""
    event = EventFactory()
    track = TrackFactory(event=event)
    other_event = EventFactory()
    TrackFactory(event=other_event)

    serializer = SpeakerInformationSerializer(
        context={"request": make_api_request(event=event)}
    )

    assert list(serializer.fields["limit_tracks"].queryset) == [track]


def test_speaker_information_serializer_init_sets_type_queryset_from_event():
    """When initialized with an event, limit_types queryset is scoped to that event."""
    event = EventFactory()
    sub_type = SubmissionTypeFactory(event=event)
    other_event = EventFactory()
    SubmissionTypeFactory(event=other_event)

    serializer = SpeakerInformationSerializer(
        context={"request": make_api_request(event=event)}
    )

    qs = set(serializer.fields["limit_types"].queryset)
    assert qs == {event.cfp.default_type, sub_type}


def test_speaker_information_serializer_init_without_event_uses_empty_querysets():
    """Without an event, limit_tracks and limit_types use empty querysets."""
    serializer = SpeakerInformationSerializer(context={"request": make_api_request()})

    assert serializer.fields["limit_tracks"].queryset.count() == 0
    assert serializer.fields["limit_types"].queryset.count() == 0


def test_speaker_information_serializer_fields():
    event = EventFactory()
    info = SpeakerInformationFactory(event=event)

    serializer = SpeakerInformationSerializer(
        info, context={"request": make_api_request(event=event)}
    )
    data = serializer.data

    assert set(data.keys()) == {
        "id",
        "target_group",
        "title",
        "text",
        "resource",
        "limit_tracks",
        "limit_types",
    }
    assert data["id"] == info.pk
    assert data["target_group"] == info.target_group


def test_speaker_information_serializer_create_sets_event():
    """create() assigns the event from the serializer context."""
    event = EventFactory()

    serializer = SpeakerInformationSerializer(
        context={"request": make_api_request(event=event)}
    )
    instance = serializer.create(
        {"title": "Info", "text": "Some text", "target_group": "accepted"}
    )

    assert instance.event == event
    assert instance.pk is not None


def test_speaker_information_serializer_create_with_resource():
    """create() saves the uploaded resource file when provided."""
    event = EventFactory()

    resource = SimpleUploadedFile(
        "guide.pdf", b"pdf-content", content_type="application/pdf"
    )
    serializer = SpeakerInformationSerializer(
        context={"request": make_api_request(event=event)}
    )
    instance = serializer.create(
        {
            "title": "Info",
            "text": "Some text",
            "target_group": "accepted",
            "resource": resource,
        }
    )

    assert instance.pk is not None
    assert instance.resource
    assert instance.resource.name.endswith(".pdf")


def test_speaker_information_serializer_create_without_resource():
    """create() works without a resource file."""
    event = EventFactory()

    serializer = SpeakerInformationSerializer(
        context={"request": make_api_request(event=event)}
    )
    instance = serializer.create(
        {"title": "Info", "text": "Some text", "target_group": "accepted"}
    )

    assert instance.pk is not None
    assert not instance.resource


def test_speaker_information_serializer_update_with_resource():
    """update() saves a new resource file on an existing instance."""
    event = EventFactory()
    info = SpeakerInformationFactory(event=event)

    resource = SimpleUploadedFile(
        "new_guide.pdf", b"new-content", content_type="application/pdf"
    )
    serializer = SpeakerInformationSerializer(
        instance=info, context={"request": make_api_request(event=event)}
    )
    serializer.update(info, {"resource": resource})

    info.refresh_from_db()
    assert info.resource
    assert info.resource.name.endswith(".pdf")


def test_speaker_information_serializer_update_without_resource():
    """update() without resource does not touch the resource field."""
    event = EventFactory()
    info = SpeakerInformationFactory(event=event, title="Original Title")

    serializer = SpeakerInformationSerializer(
        instance=info, context={"request": make_api_request(event=event)}
    )
    result = serializer.update(info, {"title": "Updated Title"})

    assert result.title == "Updated Title"


def test_speaker_information_serializer_resource_representation_without_value():
    """resource field returns None when no file is uploaded."""
    event = EventFactory()
    info = SpeakerInformationFactory(event=event)

    serializer = SpeakerInformationSerializer(
        info, context={"request": make_api_request(event=event)}
    )
    data = serializer.data

    assert data["resource"] is None
