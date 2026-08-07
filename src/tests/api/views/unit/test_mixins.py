# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from contextlib import contextmanager

import pytest
from django.db.models.signals import post_save

from pretalx.api.serializers.room import RoomOrgaSerializer
from pretalx.api.versions import CURRENT_VERSION
from pretalx.api.views.mixins import ApiVersionException
from pretalx.api.views.room import RoomViewSet
from pretalx.api.views.submission import TagViewSet
from pretalx.common.models.log import ActivityLog
from tests.factories.person import UserFactory
from tests.utils import make_api_request, make_view

pytestmark = pytest.mark.unit


@contextmanager
def failing_log_writes():
    def explode(sender, **kwargs):
        raise RuntimeError("log write failed")

    post_save.connect(explode, sender=ActivityLog)
    try:
        yield
    finally:
        post_save.disconnect(explode, sender=ActivityLog)


def test_get_versioned_serializer_rejects_unregistered_serializer():
    view = make_view(RoomViewSet, make_api_request())
    view.api_version = CURRENT_VERSION

    with pytest.raises(ApiVersionException):
        view.get_versioned_serializer("NoSuchSerializer")


def test_api_version_without_request_raises_version_exception():
    view = make_view(RoomViewSet, None)

    with pytest.raises(ApiVersionException):
        view.api_version  # noqa: B018 -- cached_property, not a no-op


@pytest.mark.django_db
def test_perform_create_rolls_back_when_log_write_fails(event):
    request = make_api_request(event=event, user=UserFactory())
    view = make_view(RoomViewSet, request)
    serializer = RoomOrgaSerializer(
        data={"name": "Rollback Room"}, context={"request": request}
    )
    assert serializer.is_valid(), serializer.errors

    with failing_log_writes(), pytest.raises(RuntimeError):
        view.perform_create(serializer)

    assert list(event.rooms.all()) == []


@pytest.mark.django_db
def test_perform_update_rolls_back_when_log_write_fails(event):
    room = event.rooms.create(name="Old name")
    request = make_api_request(event=event, user=UserFactory())
    view = make_view(RoomViewSet, request)
    serializer = RoomOrgaSerializer(
        room, data={"name": "New name"}, context={"request": request}
    )
    assert serializer.is_valid(), serializer.errors

    with failing_log_writes(), pytest.raises(RuntimeError):
        view.perform_update(serializer)

    room.refresh_from_db()
    assert str(room.name) == "Old name"


@pytest.mark.django_db
def test_perform_destroy_rolls_back_when_log_write_fails(event):
    tag = event.tags.create(tag="rollback", color="#00ff00")
    view = make_view(TagViewSet, make_api_request(event=event, user=UserFactory()))

    with failing_log_writes(), pytest.raises(RuntimeError):
        view.perform_destroy(tag)

    assert [t.tag for t in event.tags.all()] == ["rollback"]
