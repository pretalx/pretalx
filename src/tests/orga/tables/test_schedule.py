# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest

from pretalx.orga.tables.schedule import RoomTable
from tests.factories import EventFactory, RoomFactory, UserFactory

pytestmark = pytest.mark.unit


@pytest.fixture
def event():
    return EventFactory()


@pytest.mark.django_db
def test_room_table_sets_dragsort_settings(event):
    room = RoomFactory(event=event)
    table = RoomTable([room], event=event, user=UserFactory.build())

    assert table.attrs["dragsort-url"] == event.orga_urls.room_settings
    assert table.row_attrs["dragsort-id"](room) == room.pk
