# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.http import QueryDict
from django_scopes import scope

from pretalx.common.tables.filters import FilterContext, TableFilterSet
from pretalx.orga.tables.submission import ReviewTable, SubmissionTable
from pretalx.submission.enums import SubmissionStates
from pretalx.submission.interfaces.filters import review_list_filters
from tests.factories import (
    EventFactory,
    QuestionFactory,
    ReviewFactory,
    ReviewScoreCategoryFactory,
    ReviewScoreFactory,
    SpeakerFactory,
    SpeakerRoleFactory,
    SubmissionFactory,
    SubmissionTypeFactory,
    TagFactory,
    TrackFactory,
    UserFactory,
)
from tests.utils import make_orga_user, make_request

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.fixture
def event():
    return EventFactory()


@pytest.mark.parametrize(
    ("feature_flags", "kwargs", "default_columns", "exclude"),
    (
        (
            {"use_tracks": False},
            {"can_view_speakers": True, "has_update_permission": True},
            [
                "indicator",
                "title",
                "speakers",
                "submission_type",
                "state",
                "is_featured",
            ],
            [
                "track",
                "submission_type",
                "tags",
                "requires_signup",
                "attendee_signup_count",
            ],
        ),
        (
            {"use_tracks": True, "attendee_signup": True},
            {"can_view_speakers": True, "has_update_permission": True},
            [
                "indicator",
                "title",
                "speakers",
                "track",
                "submission_type",
                "state",
                "is_featured",
            ],
            ["submission_type", "tags"],
        ),
        (
            {"use_tracks": False},
            {},
            [
                "indicator",
                "title",
                "speakers",
                "submission_type",
                "state",
                "is_featured",
            ],
            [
                "track",
                "submission_type",
                "tags",
                "speakers",
                "is_featured",
                "actions",
                "requires_signup",
                "attendee_signup_count",
            ],
        ),
        (
            {"use_tracks": False},
            {"has_update_permission": True},
            [
                "indicator",
                "title",
                "speakers",
                "submission_type",
                "state",
                "is_featured",
            ],
            [
                "track",
                "submission_type",
                "tags",
                "speakers",
                "requires_signup",
                "attendee_signup_count",
            ],
        ),
    ),
    ids=(
        "all-permissions",
        "tracks-and-signup",
        "no-permissions",
        "update-without-speakers",
    ),
)
def test_submission_table_columns(feature_flags, kwargs, default_columns, exclude):
    event = EventFactory(feature_flags=feature_flags)
    if feature_flags.get("use_tracks"):
        TrackFactory(event=event)
    submission = SubmissionFactory(event=event, content_locale="en")

    table = SubmissionTable(
        [submission], event=event, user=UserFactory.build(), **kwargs
    )

    assert table.default_columns == default_columns
    assert table.exclude == exclude
    assert table.render_content_locale(submission) == "English"
    table._set_columns(["title", "state", "indicator"])
    assert table.sequence[0] == "indicator"


def test_review_table_render_scores(event):
    submission = SubmissionFactory(event=event, content_locale="en")
    table = ReviewTable([], event=event, user=UserFactory.build())

    assert table.render_median_score(3.456) == "3.5"
    assert table.render_mean_score(2.0) == "2.0"
    assert table.render_user_score(4.789) == "4.8"
    assert table.render_content_locale(submission) == "English"


@pytest.mark.parametrize(
    ("use_tracks", "kwargs", "default_columns", "exclude", "extra_columns"),
    (
        (
            False,
            {},
            ["review_count", "title", "state"],
            [
                "track",
                "submission_type",
                "tags",
                "median_score",
                "mean_score",
                "user_score",
                "speakers",
            ],
            [],
        ),
        (
            True,
            {"can_see_all_reviews": True, "aggregate_method": "median"},
            ["median_score", "review_count", "title", "track", "state"],
            ["submission_type", "tags", "mean_score", "user_score", "speakers"],
            [],
        ),
        (
            False,
            {
                "can_see_all_reviews": True,
                "aggregate_method": "mean",
                "independent_categories": True,
                "can_accept_submissions": True,
            },
            ["mean_score", "independent_score_{cat}", "review_count", "title", "state"],
            [
                "track",
                "submission_type",
                "tags",
                "median_score",
                "user_score",
                "speakers",
            ],
            ["independent_score_{cat}", "actions"],
        ),
        (
            False,
            {"is_reviewer": True, "can_view_speakers": True},
            ["user_score", "review_count", "title", "speakers", "state"],
            ["track", "submission_type", "tags", "median_score", "mean_score"],
            [],
        ),
        (
            False,
            {"is_reviewer": True},
            ["user_score", "review_count", "title", "state"],
            [
                "track",
                "submission_type",
                "tags",
                "median_score",
                "mean_score",
                "speakers",
            ],
            [],
        ),
    ),
    ids=(
        "minimal",
        "median-with-tracks",
        "mean-independent-actions",
        "reviewer-with-speakers",
        "reviewer-without-speakers",
    ),
)
def test_review_table_columns(
    use_tracks, kwargs, default_columns, exclude, extra_columns
):
    event = EventFactory(feature_flags={"use_tracks": use_tracks})
    if use_tracks:
        TrackFactory(event=event)
    cat = ReviewScoreCategoryFactory(event=event)
    if kwargs.get("independent_categories"):
        kwargs["independent_categories"] = [cat]
    base_columns = list(ReviewTable.base_columns)

    table = ReviewTable([], event=event, user=UserFactory.build(), **kwargs)

    assert table.default_columns == [c.format(cat=cat.pk) for c in default_columns]
    assert table.exclude == exclude
    assert [name for name in table.columns.names() if name not in base_columns] == [
        c.format(cat=cat.pk) for c in extra_columns
    ]


def test_review_table_get_independent_score_returns_none_without_categories(event):
    submission = SubmissionFactory(event=event)
    table = ReviewTable([], event=event, user=UserFactory.build())

    assert table.get_independent_score(submission, 999) is None


@pytest.mark.parametrize(
    ("aggregate_method", "expected"), (("mean", 2.3), ("median", 1))
)
def test_review_table_get_independent_score_with_reviews(
    event, aggregate_method, expected
):
    cat = ReviewScoreCategoryFactory(event=event)
    other_cat = ReviewScoreCategoryFactory(event=event)
    submission = SubmissionFactory(event=event)
    for value in (1, 1, 5):
        review = ReviewFactory(submission=submission)
        review.scores.add(
            ReviewScoreFactory(category=cat, value=value),
            ReviewScoreFactory(category=other_cat, value=3),
        )

    table = ReviewTable(
        [submission],
        event=event,
        user=UserFactory.build(),
        can_see_all_reviews=True,
        independent_categories=[cat],
        aggregate_method=aggregate_method,
    )

    assert table.get_independent_score(submission, cat.pk) == expected
    assert table._scores_cache == {submission.pk: {cat.pk: expected}}


def test_review_table_get_independent_score_user_only(event):
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


def test_review_table_load_all_scores_empty_data(event):
    cat = ReviewScoreCategoryFactory(event=event)
    table = ReviewTable(
        [], event=event, user=UserFactory.build(), independent_categories=[cat]
    )
    table._load_all_scores()

    assert table._scores_cache == {}


def test_review_table_get_independent_score_uses_cached_scores(event):
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


@pytest.mark.parametrize("table_class", (SubmissionTable, ReviewTable))
@pytest.mark.parametrize(
    ("sort", "expected"),
    (
        ("speakers", ["Bob talk", "Alpha", "beta", "Zed talk", "No speakers"]),
        ("-speakers", ["Zed talk", "Alpha", "beta", "Bob talk", "No speakers"]),
        (
            "speakers&sort=-title",
            ["Bob talk", "beta", "Alpha", "Zed talk", "No speakers"],
        ),
    ),
)
def test_speakers_column_sorts_by_first_speaker_effective_name(
    event, table_class, sort, expected
):
    def add_speaker(submission, position, **kwargs):
        speaker = SpeakerFactory(event=event, **kwargs)
        SpeakerRoleFactory(submission=submission, speaker=speaker, position=position)

    SubmissionFactory(event=event, title="No speakers")
    zed = SubmissionFactory(event=event, title="Zed talk")
    add_speaker(zed, 1, name="Aaron")
    add_speaker(zed, 0, name="Zed")
    bob = SubmissionFactory(event=event, title="Bob talk")
    add_speaker(bob, 0, name="", user=UserFactory(name="bob"))
    alpha = SubmissionFactory(event=event, title="Alpha")
    add_speaker(alpha, 0, name="carl")
    beta = SubmissionFactory(event=event, title="beta")
    add_speaker(beta, 0, name="Carl")
    user = make_orga_user(event)
    request = make_request(event, user, path=f"/?sort={sort}")

    with scope(event=event):
        table = table_class(
            event.submissions.all(), event=event, user=user, can_view_speakers=True
        )
        table.configure(request)
        titles = [row.record.title for row in table.rows]

    assert titles == expected


@pytest.mark.parametrize("table_class", (SubmissionTable, ReviewTable))
def test_speakers_sort_ignored_when_speakers_hidden(event, table_class):
    first = SubmissionFactory(event=event, title="First")
    SpeakerRoleFactory(
        submission=first, speaker=SpeakerFactory(event=event, name="Zed")
    )
    second = SubmissionFactory(event=event, title="Second")
    SpeakerRoleFactory(
        submission=second, speaker=SpeakerFactory(event=event, name="Adam")
    )
    user = make_orga_user(event)
    request = make_request(event, user, path="/?sort=speakers")

    with scope(event=event):
        table = table_class(
            event.submissions.order_by("pk"),
            event=event,
            user=user,
            can_view_speakers=False,
        )
        table.configure(request)
        titles = [row.record.title for row in table.rows]

    assert titles == ["First", "Second"]


def test_submission_table_self_constructs_from_event_and_user(event):
    orga = make_orga_user(event, can_change_submissions=True)
    reviewer = make_orga_user(event, is_reviewer=True, can_change_submissions=False)
    question = QuestionFactory(event=event, target="submission", variant="string")
    SubmissionTypeFactory(event=event)

    orga_table = SubmissionTable([], event=event, user=orga)
    reviewer_table = SubmissionTable([], event=event, user=reviewer)
    overridden = SubmissionTable(
        [], event=event, user=orga, has_update_permission=False, questions=[]
    )

    assert orga_table.has_update_permission is True
    assert orga_table.can_view_speakers is True
    assert f"question_{question.pk}" in orga_table.columns.names()
    assert "submission_type" not in orga_table.exclude
    assert "track" in orga_table.exclude
    assert reviewer_table.has_update_permission is False
    assert {"is_featured", "actions"} <= set(reviewer_table.exclude)
    assert overridden.has_update_permission is False
    assert overridden.questions == []


@pytest.mark.parametrize("table_class", (SubmissionTable, ReviewTable))
def test_submission_tables_column_flags_default_from_event(event, table_class):
    orga = make_orga_user(event, can_change_submissions=True)
    context = FilterContext(event=event, user=orga)
    filterset = TableFilterSet(
        review_list_filters(context), data=QueryDict("tags=1"), context=context
    )
    kwargs = {"event": event, "user": orga, "filterset": filterset}

    without_tags = table_class([], **kwargs)
    TagFactory(event=event)
    with_tags = table_class([], **kwargs)
    overridden = table_class(
        [], show_tags=False, show_tracks=True, show_submission_types=True, **kwargs
    )

    assert "tags" not in without_tags.columns.names()
    assert {"track", "submission_type"} & set(without_tags.columns.names()) == set()
    assert "tags" in with_tags.columns.names()
    assert "tags" not in overridden.columns.names()
    assert {"track", "submission_type"} <= set(overridden.columns.names())


def test_submission_table_filter_options(event):
    orga = make_orga_user(event, can_change_submissions=True)
    reviewer = make_orga_user(event, is_reviewer=True, can_change_submissions=False)
    track = TrackFactory(event=event)
    reviewer.teams.filter(is_reviewer=True).first().limit_tracks.add(track)

    orga_options = SubmissionTable.get_filter_options(event, orga)
    reviewer_options = SubmissionTable.get_filter_options(event, reviewer)

    assert orga_options == {
        "default_states": SubmissionStates.active_states,
        "can_view_speakers": True,
    }
    assert set(reviewer_options["limit_tracks"]) == {track.pk}


def test_review_table_self_constructs_from_event_and_user(event):
    orga = make_orga_user(event, can_change_submissions=True)
    category = ReviewScoreCategoryFactory(event=event, is_independent=True)
    submission = SubmissionFactory(event=event)
    ReviewFactory(submission=submission, user=orga)

    table = ReviewTable([submission], event=event, user=orga)

    assert table.can_see_all_reviews is True
    assert table.is_reviewer is True
    assert table.aggregate_method == "median"
    assert table.independent_categories == [category]
    assert table.request_user == orga
    assert list(table.submissions_reviewed) == [submission.pk]
    assert "tags" in table.exclude
    assert table.can_accept_submissions is True
    assert "actions" in table.columns.names()


def test_submission_tables_without_event_or_user_fall_back():
    assert SubmissionTable.get_can_view_speakers(None, None) is False
    assert ReviewTable.get_can_see_all_reviews(None, None) is False
    assert ReviewTable.get_filter_options(None, None) == {
        "usable_states": ReviewTable.usable_states,
        "can_view_speakers": False,
    }

    table = ReviewTable([], event=None, user=None)

    assert table.aggregate_method == "mean"
    assert table.independent_categories == []
    assert table.is_reviewer is False
    assert list(table.submissions_reviewed) == []
