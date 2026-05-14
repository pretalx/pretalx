# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import (
    Avg,
    Case,
    Count,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce

from pretalx.common.db import Median
from pretalx.submission.enums import SubmissionStates
from pretalx.submission.models import Review, Submission


def annotate_review_count(queryset):
    review_count = (
        Review.objects.filter(submission=OuterRef("pk"))
        .order_by()
        .values("submission")
        .annotate(count=Count("pk"))
        .values("count")
    )
    return queryset.annotate(review_count=Coalesce(Subquery(review_count), Value(0)))


def annotate_scored_review_count(queryset):
    return queryset.annotate(
        review_nonnull_count=Count(
            "reviews", distinct=True, filter=Q(reviews__score__isnull=False)
        )
    )


def annotate_user_review_score(queryset, user):
    user_reviews = Review.objects.filter(
        user=user, submission_id=OuterRef("pk")
    ).values("score")
    return queryset.annotate(user_score=Subquery(user_reviews))


def annotate_aggregate_scores(queryset):
    return queryset.annotate(
        median_score=Median("reviews__score", filter=Q(reviews__score__isnull=False)),
        mean_score=Avg("reviews__score", filter=Q(reviews__score__isnull=False)),
    )


def annotate_state_rank(queryset):
    return queryset.annotate(
        state_rank=Case(
            When(state=SubmissionStates.SUBMITTED, then=1),
            When(state=SubmissionStates.ACCEPTED, then=2),
            When(state=SubmissionStates.CONFIRMED, then=3),
            When(state=SubmissionStates.REJECTED, then=4),
            default=5,
            output_field=IntegerField(),
        )
    )


def review_dashboard_prefetches(queryset):
    return queryset.select_related("track", "submission_type").prefetch_related(
        "speakers",
        "reviews",
        "reviews__user",
        "reviews__scores",
        "tags",
        "answers",
        "answers__options",
        "answers__question",
    )


def review_view_submissions(event):
    return event.submissions.with_sorted_speakers().prefetch_related(
        "resources",
        Prefetch(
            "speakers__submissions", queryset=Submission.objects.select_related("event")
        ),
    )
