# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.orga.tables.schedule import RoomTable
from pretalx.schedule.models import Room
from tests.factories import EventFactory, RoomFactory, UserFactory

pytestmark = pytest.mark.unit


@pytest.fixture
def event():
    return EventFactory()


def test_room_table_meta_model():
    assert RoomTable.Meta.model == Room


def test_room_table_meta_fields():
    assert RoomTable.Meta.fields == ("name", "capacity", "guid")


def test_room_table_default_columns():
    assert RoomTable.default_columns == ("name",)


def test_room_table_has_empty_text():
    assert RoomTable.empty_text


@pytest.mark.django_db
def test_room_table_sets_dragsort_url(event):
    room = RoomFactory(event=event)
    table = RoomTable([room], event=event, user=UserFactory.build())

    assert table.attrs["dragsort-url"] == event.orga_urls.room_settings


@pytest.mark.django_db
def test_room_table_is_unsortable(event):
    """RoomTable uses UnsortableMixin, so orderable should be False."""
    room = RoomFactory(event=event)
    table = RoomTable([room], event=event, user=UserFactory.build())

    assert table.orderable is False


@pytest.mark.django_db
def test_room_table_row_attrs_include_dragsort_id(event):
    room = RoomFactory(event=event)
    table = RoomTable([room], event=event, user=UserFactory.build())

    dragsort_id_func = table.Meta.row_attrs["dragsort-id"]
    assert dragsort_id_func(room) == room.pk
