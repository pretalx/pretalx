# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import pytest
from django.http import QueryDict

from pretalx.common.tables.filters import FilterContext, TableFilterSet
from pretalx.orga.tables.review import ReviewExportTable, review_export_filters
from pretalx.submission.enums import SubmissionStates
from tests.factories import (
    ReviewFactory,
    ReviewScoreCategoryFactory,
    ReviewScoreFactory,
    SubmissionFactory,
    UserFactory,
)
from tests.utils import make_orga_user

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_review_export_table_adds_score_category_columns_when_several(event):
    single = ReviewExportTable([], event=event, user=UserFactory.build())
    extra = ReviewScoreCategoryFactory(event=event, name="Novelty")

    multiple = ReviewExportTable([], event=event, user=UserFactory.build())

    assert not [name for name in single.columns.names() if name.startswith("score_")]
    assert f"score_{extra.pk}" in multiple.columns.names()
    assert (
        str(multiple.columns[f"score_{extra.pk}"].verbose_name) == "Score in “Novelty”"
    )
    assert ReviewExportTable.get_score_categories(None) == []


def test_review_export_table_reviewer_columns_need_permission(event):
    orga = make_orga_user(event, can_change_submissions=True)
    reviewer = make_orga_user(event, is_reviewer=True, can_change_submissions=False)
    event.active_review_phase.can_see_reviewer_names = False
    event.active_review_phase.save()

    orga_table = ReviewExportTable([], event=event, user=orga)
    reviewer_table = ReviewExportTable([], event=event, user=reviewer)

    assert "user_name" not in orga_table.exclude
    assert {"user_name", "user_email"} <= set(reviewer_table.exclude)


def test_review_export_table_values(event):
    orga = make_orga_user(event, can_change_submissions=True)
    category = ReviewScoreCategoryFactory(event=event, name="Novelty")
    other = ReviewScoreCategoryFactory(event=event, name="Other")
    submission = SubmissionFactory(event=event, title="Talk")
    review = ReviewFactory(submission=submission, score=3, text="Great")
    review.scores.add(ReviewScoreFactory(category=category, value=4))
    table = ReviewExportTable(
        ReviewExportTable.base_queryset(event, orga), event=event, user=orga
    )
    table.configure_export(
        [
            "submission_code",
            "submission_title",
            "user_name",
            "score",
            f"score_{category.pk}",
            f"score_{other.pk}",
            "text",
        ]
    )

    rows = list(table.as_values())

    assert rows[0][:2] == ["ID", "Proposal ID"]
    assert rows[1] == [
        review.pk,
        submission.code,
        "Talk",
        review.user.name,
        review.score,
        4,
        None,
        "Great",
    ]


def test_review_export_table_anonymises_title_for_reviewers(event):
    reviewer = make_orga_user(event, is_reviewer=True, can_change_submissions=False)
    event.active_review_phase.can_see_speaker_names = False
    event.active_review_phase.save()
    submission = SubmissionFactory(
        event=event, title="Real", anonymised={"_anonymised": True, "title": "Hidden"}
    )
    review = ReviewFactory(submission=submission, user=reviewer)
    table = ReviewExportTable(
        ReviewExportTable.base_queryset(event, reviewer), event=event, user=reviewer
    )
    table.configure_export(["submission_title"])

    rows = list(table.as_values())

    assert rows[1] == [review.pk, "Hidden"]


def test_review_export_filters_by_submission_state(event):
    orga = make_orga_user(event, can_change_submissions=True)
    accepted = ReviewFactory(
        submission=SubmissionFactory(event=event, state=SubmissionStates.ACCEPTED)
    )
    ReviewFactory(
        submission=SubmissionFactory(event=event, state=SubmissionStates.REJECTED)
    )
    context = FilterContext(event=event, user=orga)
    filterset = TableFilterSet(
        review_export_filters(context),
        data=QueryDict("state=accepted"),
        context=context,
    )

    result = filterset.filter(ReviewExportTable.base_queryset(event, orga))

    assert list(result) == [accepted]
    assert [choice.value for choice in filterset.filters["state"].choices] == [
        "submitted",
        "accepted",
        "confirmed",
        "rejected",
    ]


def test_review_export_base_queryset_limits_to_own_reviews_without_list_all(event):
    orga = make_orga_user(event, can_change_submissions=True)
    reviewer = make_orga_user(event, is_reviewer=True, can_change_submissions=False)
    event.active_review_phase.can_see_other_reviews = "never"
    event.active_review_phase.save()
    submission = SubmissionFactory(event=event)
    own = ReviewFactory(submission=submission, user=reviewer)
    other = ReviewFactory(submission=submission)

    assert set(ReviewExportTable.base_queryset(event, orga)) == {own, other}
    assert set(ReviewExportTable.base_queryset(event, reviewer)) == {own}
