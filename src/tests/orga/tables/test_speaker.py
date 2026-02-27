# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scopes_disabled

from pretalx.orga.tables.speaker import (
    SpeakerInformationTable,
    SpeakerOrgaTable,
    SpeakerTable,
)
from pretalx.person.models import SpeakerInformation, SpeakerProfile
from tests.factories import (
    EventFactory,
    QuestionFactory,
    SpeakerFactory,
    SpeakerInformationFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def event():
    with scopes_disabled():
        return EventFactory()


def test_speaker_information_table_meta_model():
    assert SpeakerInformationTable.Meta.model == SpeakerInformation


def test_speaker_information_table_meta_fields():
    assert SpeakerInformationTable.Meta.fields == (
        "title",
        "target_group",
        "limit_tracks",
        "limit_types",
        "resource",
    )


@pytest.mark.parametrize(
    ("use_tracks", "expected"),
    (
        (True, ["title", "limit_types", "limit_tracks", "resource"]),
        (False, ["title", "limit_types", "resource"]),
    ),
)
@pytest.mark.django_db
def test_speaker_information_table_default_columns(event, use_tracks, expected):
    event.feature_flags["use_tracks"] = use_tracks
    event.save()
    with scopes_disabled():
        info = SpeakerInformationFactory(event=event)
    table = SpeakerInformationTable([info], event=event, user=UserFactory.build())

    assert table.default_columns == expected


@pytest.mark.parametrize("use_tracks", (True, False))
@pytest.mark.django_db
def test_speaker_information_table_limit_tracks_excluded_by_feature(event, use_tracks):
    event.feature_flags["use_tracks"] = use_tracks
    event.save()
    with scopes_disabled():
        info = SpeakerInformationFactory(event=event)
    table = SpeakerInformationTable([info], event=event, user=UserFactory.build())

    assert ("limit_tracks" in table.exclude) != use_tracks


@pytest.mark.django_db
def test_speaker_information_table_render_resource(event):
    with scopes_disabled():
        info = SpeakerInformationFactory(event=event)
    table = SpeakerInformationTable([info], event=event, user=UserFactory.build())

    result = table.render_resource(info)

    assert "fa-file-o" in result


def test_speaker_table_meta_model():
    assert SpeakerTable.Meta.model == SpeakerProfile


def test_speaker_table_meta_fields():
    assert SpeakerTable.Meta.fields == (
        "name",
        "code",
        "email",
        "submission_count",
        "accepted_submission_count",
        "locale",
        "has_arrived",
    )


def test_speaker_table_default_columns():
    assert SpeakerTable.default_columns == (
        "name",
        "submission_count",
        "accepted_submission_count",
        "has_arrived",
    )


@pytest.mark.django_db
def test_speaker_table_stores_has_arrived_permission(event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
    table = SpeakerTable(
        [speaker], event=event, user=UserFactory.build(), has_arrived_permission=True
    )

    assert table.has_arrived_permission is True


@pytest.mark.django_db
def test_speaker_table_has_arrived_permission_defaults_false(event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
    table = SpeakerTable([speaker], event=event, user=UserFactory.build())

    assert table.has_arrived_permission is False


@pytest.mark.django_db
def test_speaker_table_stores_short_questions(event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
        q1 = QuestionFactory(event=event, target="speaker")
        q2 = QuestionFactory(event=event, target="speaker")
    table = SpeakerTable(
        [speaker], event=event, user=UserFactory.build(), short_questions=[q1, q2]
    )

    assert table.short_questions == [q1, q2]


@pytest.mark.django_db
def test_speaker_table_short_questions_defaults_empty(event):
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
    table = SpeakerTable([speaker], event=event, user=UserFactory.build())

    assert table.short_questions == []


def test_speaker_orga_table_meta_model():
    assert SpeakerOrgaTable.Meta.model == SpeakerProfile


def test_speaker_orga_table_meta_fields():
    assert SpeakerOrgaTable.Meta.fields == (
        "name",
        "email",
        "submission_count",
        "accepted_submission_count",
    )


def test_speaker_orga_table_nulled_columns():
    """SpeakerOrgaTable sets unavailable columns to None."""
    assert SpeakerOrgaTable.locale is None
    assert SpeakerOrgaTable.code is None
    assert SpeakerOrgaTable.has_arrived is None
    assert SpeakerOrgaTable.default_columns is None


@pytest.mark.django_db
def test_speaker_orga_table_paginated_rows_is_cached(event):
    """paginated_rows is a cached_property so repeated access returns the same object."""
    with scopes_disabled():
        speaker = SpeakerFactory(event=event)
    table = SpeakerOrgaTable([speaker], event=event, user=UserFactory.build())

    first = table.paginated_rows
    second = table.paginated_rows

    assert first is second
