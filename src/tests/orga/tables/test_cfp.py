# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.utils.html import format_html

from pretalx.orga.tables.cfp import (
    QuestionTable,
    SubmissionTypeTable,
    SubmitterAccessCodeTable,
    TrackTable,
)
from tests.factories import (
    EventFactory,
    QuestionFactory,
    SubmitterAccessCodeFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_orga_user, make_request

pytestmark = pytest.mark.unit


@pytest.fixture
def event():
    return EventFactory()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("maximum_uses", "redeemed", "expected"),
    ((5, 2, "2 / 5"), (None, 3, "3 / ∞ "), (10, 0, "0 / 10")),
)
def test_submitter_access_code_table_render_uses(
    event, maximum_uses, redeemed, expected
):
    code = SubmitterAccessCodeFactory(
        event=event, maximum_uses=maximum_uses, redeemed=redeemed
    )
    table = SubmitterAccessCodeTable([code], event=event, user=UserFactory.build())

    assert table.render_uses(code) == expected


@pytest.mark.django_db
@pytest.mark.parametrize(("maximum_uses", "expected"), ((7, 7), (None, "∞")))
def test_submitter_access_code_table_render_maximum_uses(event, maximum_uses, expected):
    code = SubmitterAccessCodeFactory(event=event, maximum_uses=maximum_uses)
    table = SubmitterAccessCodeTable([code], event=event, user=UserFactory.build())

    assert table.render_maximum_uses(code) == expected


@pytest.mark.django_db
def test_submitter_access_code_table_excludes_tracks_when_feature_disabled():
    """When use_tracks feature flag is off, the tracks column is excluded."""
    event = EventFactory(feature_flags={"use_tracks": False})

    code = SubmitterAccessCodeFactory(event=event)
    table = SubmitterAccessCodeTable([code], event=event, user=UserFactory.build())

    assert "tracks" in table.exclude


@pytest.mark.django_db
def test_submitter_access_code_table_includes_tracks_when_feature_enabled():
    event = EventFactory(feature_flags={"use_tracks": True})

    code = SubmitterAccessCodeFactory(event=event)
    table = SubmitterAccessCodeTable([code], event=event, user=UserFactory.build())

    assert "tracks" not in table.exclude


def test_submitter_access_code_table_default_columns():
    assert SubmitterAccessCodeTable.default_columns == (
        "code",
        "tracks",
        "submission_types",
        "valid_until",
        "uses",
    )


@pytest.mark.django_db
def test_track_table_sets_dragsort_url(event):
    track = TrackFactory(event=event)
    table = TrackTable([track], event=event, user=UserFactory.build())

    assert table.attrs["dragsort-url"] == event.cfp.urls.tracks


@pytest.mark.django_db
def test_track_table_is_unsortable(event):
    """UnsortableMixin forces orderable=False without the caller passing it."""
    track = TrackFactory(event=event)
    table = TrackTable([track], event=event, user=UserFactory.build())

    assert table.orderable is False


@pytest.mark.django_db
def test_track_table_row_attrs_include_dragsort_id(event):
    track = TrackFactory(event=event)

    dragsort_id_func = TrackTable.Meta.row_attrs["dragsort-id"]
    assert dragsort_id_func(track) == track.pk


def test_track_table_default_columns():
    assert TrackTable.default_columns == ("name", "color", "proposals")


def test_submission_type_table_default_columns():
    assert SubmissionTypeTable.default_columns == (
        "name",
        "proposals",
        "default_duration",
    )


@pytest.mark.django_db
def test_question_table_sets_dragsort_url(event):
    question = QuestionFactory(event=event)
    table = QuestionTable([question], event=event, user=UserFactory.build())

    assert table.attrs["dragsort-url"] == event.cfp.urls.questions


@pytest.mark.django_db
def test_question_table_is_unsortable(event):
    """UnsortableMixin forces orderable=False without the caller passing it."""
    question = QuestionFactory(event=event)
    table = QuestionTable([question], event=event, user=UserFactory.build())

    assert table.orderable is False


@pytest.mark.django_db
def test_question_table_row_attrs_include_dragsort_id(event):
    question = QuestionFactory(event=event)

    dragsort_id_func = QuestionTable.Meta.row_attrs["dragsort-id"]
    assert dragsort_id_func(question) == question.pk


def test_question_table_default_columns():
    assert QuestionTable.default_columns == (
        "question",
        "target",
        "variant",
        "required",
        "active",
        "answer_count",
    )


@pytest.mark.django_db
def test_question_table_render_question_links_to_base_when_user_has_answer_access(
    event,
):
    """When user has answer access to a question, render_question links to urls.base."""
    user = make_orga_user(event, can_change_submissions=True)
    question = QuestionFactory(event=event)
    request = make_request(event, user=user)
    table = QuestionTable([question], event=event, user=user)
    table.request = request

    result = table.render_question(question, str(question.question))

    expected = format_html(
        '<a href="{}">{}</a>', question.urls.base, str(question.question)
    )
    assert result == expected


@pytest.mark.django_db
def test_question_table_render_question_links_to_edit_when_no_answer_access(event):
    """When user lacks answer access, render_question links to urls.edit."""
    user = make_orga_user(event, can_change_submissions=False, all_events=False)
    question = QuestionFactory(event=event)
    request = make_request(event, user=user)
    table = QuestionTable([question], event=event, user=user)
    table.request = request

    result = table.render_question(question, str(question.question))

    expected = format_html(
        '<a href="{}">{}</a>', question.urls.edit, str(question.question)
    )
    assert result == expected


@pytest.mark.django_db
def test_question_table_render_question_returns_plain_value_without_request(event):
    """When no request is set, render_question returns the plain value."""
    question = QuestionFactory(event=event)
    table = QuestionTable([question], event=event, user=None)

    result = table.render_question(question, "My question text")

    assert result == "My question text"


@pytest.mark.django_db
def test_question_table_accessible_question_ids_empty_without_user(event):
    question = QuestionFactory(event=event)
    table = QuestionTable([question], event=event, user=None)

    assert table._accessible_question_ids == set()


@pytest.mark.django_db
def test_question_table_accessible_question_ids_populated_for_orga_user(event):
    user = make_orga_user(event, can_change_submissions=True)
    q1 = QuestionFactory(event=event)
    q2 = QuestionFactory(event=event)
    table = QuestionTable([q1, q2], event=event, user=user)

    accessible_ids = table._accessible_question_ids

    assert accessible_ids == {q1.pk, q2.pk}
