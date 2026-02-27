# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django_scopes import scopes_disabled

from pretalx.orga.tables.submission import ReviewTable, SubmissionTable, TagTable
from pretalx.submission.models import Submission, Tag
from tests.factories import (
    EventFactory,
    QuestionFactory,
    ReviewFactory,
    ReviewScoreCategoryFactory,
    ReviewScoreFactory,
    SubmissionFactory,
    UserFactory,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def event():
    with scopes_disabled():
        return EventFactory()


def test_submission_table_meta_model():
    assert SubmissionTable.Meta.model == Submission


def test_submission_table_exempt_columns():
    assert SubmissionTable.exempt_columns == ("pk", "actions", "indicator")


@pytest.mark.parametrize(
    ("use_tracks", "expected"),
    (
        (
            False,
            [
                "indicator",
                "title",
                "speakers",
                "submission_type",
                "state",
                "is_featured",
            ],
        ),
        (
            True,
            [
                "indicator",
                "title",
                "speakers",
                "track",
                "submission_type",
                "state",
                "is_featured",
            ],
        ),
    ),
)
@pytest.mark.django_db
def test_submission_table_default_columns(event, use_tracks, expected):
    event.feature_flags["use_tracks"] = use_tracks
    event.save()
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
    table = SubmissionTable(
        [submission], event=event, user=UserFactory.build(), can_view_speakers=True
    )

    assert table.default_columns == expected


@pytest.mark.parametrize("can_view_speakers", (True, False))
@pytest.mark.django_db
def test_submission_table_speakers_excluded_by_permission(event, can_view_speakers):
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
    table = SubmissionTable(
        [submission],
        event=event,
        user=UserFactory.build(),
        can_view_speakers=can_view_speakers,
    )

    assert ("speakers" in table.exclude) != can_view_speakers


@pytest.mark.parametrize("has_update_permission", (True, False))
@pytest.mark.django_db
def test_submission_table_actions_excluded_by_permission(event, has_update_permission):
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
    table = SubmissionTable(
        [submission],
        event=event,
        user=UserFactory.build(),
        has_update_permission=has_update_permission,
    )

    assert ("is_featured" in table.exclude) != has_update_permission
    assert ("actions" in table.exclude) != has_update_permission


@pytest.mark.django_db
def test_submission_table_render_content_locale(event):
    with scopes_disabled():
        submission = SubmissionFactory(event=event, content_locale="en")
    table = SubmissionTable(
        [submission], event=event, user=UserFactory.build(), can_view_speakers=True
    )

    result = table.render_content_locale(submission)

    assert result == submission.get_content_locale_display()


@pytest.mark.django_db
def test_submission_table_set_columns_keeps_indicator_first(event):
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
    table = SubmissionTable(
        [submission], event=event, user=UserFactory.build(), can_view_speakers=True
    )

    table._set_columns(["title", "state", "indicator"])

    assert table.sequence[0] == "indicator"


@pytest.mark.django_db
def test_submission_table_stores_short_questions(event):
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
        question = QuestionFactory(event=event)
    table = SubmissionTable(
        [submission], event=event, user=UserFactory.build(), short_questions=[question]
    )

    assert table.short_questions == [question]


@pytest.mark.django_db
def test_submission_table_short_questions_defaults_empty(event):
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
    table = SubmissionTable([submission], event=event, user=UserFactory.build())

    assert table.short_questions == []


def test_review_table_meta_model():
    assert ReviewTable.Meta.model == Submission


@pytest.mark.django_db
def test_review_table_meta_row_attrs_class(event):
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
    class_func = ReviewTable.Meta.row_attrs["class"]

    assert class_func(submission) == submission.state


@pytest.mark.django_db
def test_review_table_render_median_score(event):
    table = ReviewTable([], event=event, user=UserFactory.build())

    assert table.render_median_score(3.456) == "3.5"


@pytest.mark.django_db
def test_review_table_render_mean_score(event):
    table = ReviewTable([], event=event, user=UserFactory.build())

    assert table.render_mean_score(2.0) == "2.0"


@pytest.mark.django_db
def test_review_table_render_user_score(event):
    table = ReviewTable([], event=event, user=UserFactory.build())

    assert table.render_user_score(4.789) == "4.8"


@pytest.mark.django_db
def test_review_table_render_content_locale(event):
    with scopes_disabled():
        submission = SubmissionFactory(event=event, content_locale="en")
    table = ReviewTable([], event=event, user=UserFactory.build())

    result = table.render_content_locale(submission)

    assert result == submission.get_content_locale_display()


@pytest.mark.parametrize(
    ("aggregate_method", "excluded", "included"),
    (("median", "mean_score", "median_score"), ("mean", "median_score", "mean_score")),
)
@pytest.mark.django_db
def test_review_table_excludes_opposite_aggregate_score(
    event, aggregate_method, excluded, included
):
    table = ReviewTable(
        [],
        event=event,
        user=UserFactory.build(),
        can_see_all_reviews=True,
        aggregate_method=aggregate_method,
    )

    assert excluded in table.exclude
    assert included not in table.exclude


@pytest.mark.django_db
def test_review_table_excludes_both_scores_when_cannot_see_reviews(event):
    table = ReviewTable(
        [], event=event, user=UserFactory.build(), can_see_all_reviews=False
    )

    assert "median_score" in table.exclude
    assert "mean_score" in table.exclude


@pytest.mark.parametrize("is_reviewer", (True, False))
@pytest.mark.django_db
def test_review_table_user_score_excluded_by_reviewer_status(event, is_reviewer):
    table = ReviewTable(
        [], event=event, user=UserFactory.build(), is_reviewer=is_reviewer
    )

    assert ("user_score" in table.exclude) != is_reviewer


@pytest.mark.parametrize("can_view_speakers", (True, False))
@pytest.mark.django_db
def test_review_table_speakers_excluded_by_permission(event, can_view_speakers):
    table = ReviewTable(
        [], event=event, user=UserFactory.build(), can_view_speakers=can_view_speakers
    )

    assert ("speakers" in table.exclude) != can_view_speakers


@pytest.mark.django_db
def test_review_table_default_columns_minimal(event):
    """With no special permissions and no tracks, only review_count, title, and state show."""
    event.feature_flags["use_tracks"] = False
    event.save()
    table = ReviewTable(
        [],
        event=event,
        user=UserFactory.build(),
        can_see_all_reviews=False,
        is_reviewer=False,
        can_view_speakers=False,
    )

    assert table.default_columns == ["review_count", "title", "state"]


@pytest.mark.parametrize(
    ("aggregate_method", "expected_first", "excluded"),
    (("median", "median_score", "mean_score"), ("mean", "mean_score", "median_score")),
)
@pytest.mark.django_db
def test_review_table_default_columns_aggregate_method(
    event, aggregate_method, expected_first, excluded
):
    table = ReviewTable(
        [],
        event=event,
        user=UserFactory.build(),
        can_see_all_reviews=True,
        aggregate_method=aggregate_method,
    )

    assert table.default_columns[0] == expected_first
    assert excluded not in table.default_columns


@pytest.mark.django_db
def test_review_table_default_columns_with_user_score(event):
    table = ReviewTable(
        [],
        event=event,
        user=UserFactory.build(),
        is_reviewer=True,
        can_see_all_reviews=False,
    )

    assert "user_score" in table.default_columns


@pytest.mark.django_db
def test_review_table_default_columns_with_speakers(event):
    table = ReviewTable(
        [], event=event, user=UserFactory.build(), can_view_speakers=True
    )

    assert "speakers" in table.default_columns


@pytest.mark.parametrize("use_tracks", (True, False))
@pytest.mark.django_db
def test_review_table_default_columns_tracks(event, use_tracks):
    event.feature_flags["use_tracks"] = use_tracks
    event.save()
    table = ReviewTable([], event=event, user=UserFactory.build())

    assert ("track" in table.default_columns) == use_tracks


@pytest.mark.django_db
def test_review_table_default_columns_with_independent_categories(event):
    with scopes_disabled():
        cat = ReviewScoreCategoryFactory(event=event)
    table = ReviewTable(
        [],
        event=event,
        user=UserFactory.build(),
        can_see_all_reviews=True,
        independent_categories=[cat],
        aggregate_method="mean",
    )

    assert f"independent_score_{cat.pk}" in table.default_columns


@pytest.mark.django_db
def test_review_table_adds_independent_score_columns(event):
    with scopes_disabled():
        cat = ReviewScoreCategoryFactory(event=event)
    table = ReviewTable(
        [], event=event, user=UserFactory.build(), independent_categories=[cat]
    )

    column_names = list(table.columns.names())
    assert f"independent_score_{cat.pk}" in column_names


@pytest.mark.django_db
def test_review_table_adds_actions_column_when_can_accept(event):
    table = ReviewTable(
        [], event=event, user=UserFactory.build(), can_accept_submissions=True
    )

    column_names = list(table.columns.names())
    assert "actions" in column_names
    assert table.include_before_table == "orga/tables/review_table.html#before"
    assert table.include_after_table == "orga/tables/review_table.html#after"


@pytest.mark.django_db
def test_review_table_no_actions_column_when_cannot_accept(event):
    table = ReviewTable(
        [], event=event, user=UserFactory.build(), can_accept_submissions=False
    )

    column_names = list(table.columns.names())
    assert "actions" not in column_names


@pytest.mark.django_db
def test_review_table_get_independent_score_returns_none_without_categories(event):
    with scopes_disabled():
        submission = SubmissionFactory(event=event)
    table = ReviewTable([], event=event, user=UserFactory.build())

    assert table.get_independent_score(submission, 999) is None


@pytest.mark.django_db
def test_review_table_get_independent_score_with_reviews(event):
    """Scores are aggregated as mean when user can see all reviews."""
    with scopes_disabled():
        cat = ReviewScoreCategoryFactory(event=event)
        submission = SubmissionFactory(event=event)
        review1 = ReviewFactory(submission=submission)
        review2 = ReviewFactory(submission=submission)
        score1 = ReviewScoreFactory(category=cat, value=3)
        score2 = ReviewScoreFactory(category=cat, value=5)
        review1.scores.add(score1)
        review2.scores.add(score2)

        table = ReviewTable(
            [submission],
            event=event,
            user=UserFactory.build(),
            can_see_all_reviews=True,
            independent_categories=[cat],
        )
        score = table.get_independent_score(submission, cat.pk)

    assert score == 4.0


@pytest.mark.django_db
def test_review_table_get_independent_score_user_only(event):
    """When can_see_all_reviews is False, only the request user's scores are shown."""
    with scopes_disabled():
        cat = ReviewScoreCategoryFactory(event=event)
        submission = SubmissionFactory(event=event)
        user = UserFactory()
        other_user = UserFactory()
        review_mine = ReviewFactory(submission=submission, user=user)
        review_other = ReviewFactory(submission=submission, user=other_user)
        score_mine = ReviewScoreFactory(category=cat, value=7)
        score_other = ReviewScoreFactory(category=cat, value=2)
        review_mine.scores.add(score_mine)
        review_other.scores.add(score_other)

        table = ReviewTable(
            [submission],
            event=event,
            user=UserFactory.build(),
            can_see_all_reviews=False,
            independent_categories=[cat],
            request_user=user,
        )
        score = table.get_independent_score(submission, cat.pk)

    assert score == 7


@pytest.mark.django_db
def test_review_table_load_all_scores_empty_data(event):
    """_load_all_scores handles empty table data gracefully."""
    with scopes_disabled():
        cat = ReviewScoreCategoryFactory(event=event)
        table = ReviewTable(
            [], event=event, user=UserFactory.build(), independent_categories=[cat]
        )
        table._load_all_scores()

    assert table._scores_cache == {}


@pytest.mark.django_db
def test_review_table_get_independent_score_uses_cached_scores(event):
    """When _scores_cache already exists, get_independent_score uses it without reloading."""
    with scopes_disabled():
        cat = ReviewScoreCategoryFactory(event=event)
        submission = SubmissionFactory(event=event)

    table = ReviewTable(
        [submission],
        event=event,
        user=UserFactory.build(),
        independent_categories=[cat],
    )
    table._scores_cache = {submission.pk: {cat.pk: 9.9}}

    score = table.get_independent_score(submission, cat.pk)

    assert score == 9.9


@pytest.mark.django_db
def test_review_table_load_all_scores_ignores_non_independent_categories(event):
    """Scores for categories not in independent_categories are not included."""
    with scopes_disabled():
        cat = ReviewScoreCategoryFactory(event=event)
        other_cat = ReviewScoreCategoryFactory(event=event)
        submission = SubmissionFactory(event=event)
        review = ReviewFactory(submission=submission)
        score_independent = ReviewScoreFactory(category=cat, value=5)
        score_other = ReviewScoreFactory(category=other_cat, value=3)
        review.scores.add(score_independent, score_other)

        table = ReviewTable(
            [submission],
            event=event,
            user=UserFactory.build(),
            can_see_all_reviews=True,
            independent_categories=[cat],
        )
        table._load_all_scores()

    assert submission.pk in table._scores_cache
    assert cat.pk in table._scores_cache[submission.pk]
    assert other_cat.pk not in table._scores_cache[submission.pk]


def test_tag_table_meta_model():
    assert TagTable.Meta.model == Tag


def test_tag_table_meta_fields():
    assert TagTable.Meta.fields == ("tag", "color", "proposals", "is_public", "actions")


def test_tag_table_default_columns():
    assert TagTable.default_columns == ("tag", "color", "proposals")
