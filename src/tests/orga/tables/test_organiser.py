# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scopes_disabled

from pretalx.event.models import Team
from pretalx.orga.tables.organiser import TeamTable
from tests.factories import EventFactory, TeamFactory, UserFactory

pytestmark = pytest.mark.unit


@pytest.fixture
def event():
    with scopes_disabled():
        return EventFactory()


def test_team_table_meta_model():
    assert TeamTable.Meta.model == Team


def test_team_table_meta_fields():
    assert TeamTable.Meta.fields == (
        "name",
        "member_count",
        "all_events",
        "is_reviewer",
        "actions",
    )


def test_team_table_has_empty_text():
    assert "team" in str(TeamTable.empty_text).lower()


@pytest.mark.django_db
def test_team_table_renders_with_team_data(event):
    with scopes_disabled():
        team = TeamFactory(
            organiser=event.organiser, all_events=True, is_reviewer=False
        )
    table = TeamTable([team], event=event, user=UserFactory.build())

    column_names = set(table.columns.names())

    assert column_names == {
        "name",
        "member_count",
        "all_events",
        "is_reviewer",
        "actions",
    }
