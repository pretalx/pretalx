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
from pretalx.submission.enums import QuestionTarget
from tests.factories import (
    EventFactory,
    QuestionFactory,
    SubmitterAccessCodeFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_orga_user, make_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.fixture
def event():
    return EventFactory()


@pytest.mark.parametrize(
    ("maximum_uses", "redeemed", "uses", "maximum"),
    ((5, 2, "2 / 5", 5), (None, 3, "3 / ∞ ", "∞"), (10, 0, "0 / 10", 10)),
)
def test_submitter_access_code_table_render_uses(
    event, maximum_uses, redeemed, uses, maximum
):
    code = SubmitterAccessCodeFactory(
        event=event, maximum_uses=maximum_uses, redeemed=redeemed
    )
    table = SubmitterAccessCodeTable([code], event=event, user=UserFactory.build())

    assert table.render_uses(code) == uses
    assert table.render_maximum_uses(code) == maximum


@pytest.mark.parametrize("use_tracks", (False, True), ids=("disabled", "enabled"))
def test_submitter_access_code_table_tracks_column_follows_feature(use_tracks):
    event = EventFactory(feature_flags={"use_tracks": use_tracks})
    if use_tracks:
        TrackFactory(event=event)

    code = SubmitterAccessCodeFactory(event=event)
    table = SubmitterAccessCodeTable([code], event=event, user=UserFactory.build())

    assert ("tracks" in table.exclude) is not use_tracks


def test_track_table_sets_dragsort_url(event):
    track = TrackFactory(event=event)
    table = TrackTable([track], event=event, user=UserFactory.build())

    assert table.attrs["dragsort-url"] == event.cfp.urls.tracks


@pytest.mark.parametrize(
    ("table_class", "record_factory"),
    (
        (TrackTable, lambda event: TrackFactory(event=event)),
        (SubmissionTypeTable, lambda event: event.cfp.default_type),
    ),
    ids=("track", "submission_type"),
)
@pytest.mark.parametrize(
    ("flag_enabled", "excluded"),
    ((False, True), (True, False)),
    ids=("disabled", "enabled"),
)
def test_table_attendee_signup_column_visibility(
    table_class, record_factory, flag_enabled, excluded
):
    event = EventFactory(feature_flags={"attendee_signup": flag_enabled})
    record = record_factory(event)

    table = table_class([record], event=event, user=UserFactory.build())

    assert ("attendee_signup_required" in table.exclude) is excluded


def test_question_table_name_and_dragsort_url_are_target_specific(event):
    question = QuestionFactory(event=event)
    table = QuestionTable(
        [question],
        event=event,
        user=UserFactory.build(),
        target="speakers",
        list_url=event.cfp.urls.questions,
    )

    assert table.name == "QuestionTable-speakers"
    assert table.attrs["dragsort-url"] == f"{event.cfp.urls.questions}?target=speakers"


def test_question_table_render_question_links_to_base_when_user_has_answer_access(
    event,
):
    user = make_orga_user(event, can_change_submissions=True)
    q1 = QuestionFactory(event=event)
    q2 = QuestionFactory(event=event)
    table = QuestionTable(
        [q1, q2],
        event=event,
        user=user,
        target="sessions",
        list_url=event.cfp.urls.questions,
    )
    table.request = make_request(event, user=user)

    assert table._accessible_question_ids == {q1.pk, q2.pk}
    assert table.render_question(q1, str(q1.question)) == format_html(
        '<a href="{}">{}</a>', q1.urls.base, str(q1.question)
    )


def test_question_table_render_question_links_to_edit_when_no_answer_access(event):
    user = make_orga_user(event, can_change_submissions=False, all_events=False)
    question = QuestionFactory(event=event)
    table = QuestionTable(
        [question],
        event=event,
        user=user,
        target="sessions",
        list_url=event.cfp.urls.questions,
    )
    table.request = make_request(event, user=user)

    assert table.render_question(question, str(question.question)) == format_html(
        '<a href="{}">{}</a>', question.urls.edit, str(question.question)
    )


def test_question_table_render_question_returns_plain_value_without_request(event):
    question = QuestionFactory(event=event)
    table = QuestionTable(
        [question],
        event=event,
        user=None,
        target="sessions",
        list_url=event.cfp.urls.questions,
    )

    assert table._accessible_question_ids == set()
    assert table.render_question(question, "My question text") == "My question text"


def test_question_table_accessible_question_ids_empty_without_list_permission(event):
    user = make_orga_user(
        event, can_change_submissions=False, can_change_event_settings=True
    )
    question = QuestionFactory(event=event, target=QuestionTarget.REVIEWER)
    table = QuestionTable(
        [question],
        event=event,
        user=user,
        target="reviews",
        list_url=event.orga_urls.review_questions,
    )

    assert table._accessible_question_ids == set()
