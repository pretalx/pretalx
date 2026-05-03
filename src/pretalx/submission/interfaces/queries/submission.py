# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Count, Exists, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from pretalx.person.rules import is_only_reviewer
from pretalx.submission.models import Review, SubmissionStates


def annotate_assigned_reviews(queryset, event, user):
    if "is_assigned" in queryset.query.annotations:
        return queryset
    assigned = user.assigned_reviews.filter(event=event, pk=OuterRef("pk"))
    return queryset.annotate(is_assigned=Exists(Subquery(assigned)))


def submissions_for_reviewer(queryset, event, user):
    if not (phase := event.active_review_phase):
        queryset = event.submissions.none()
    queryset = queryset.exclude(speakers__user=user)
    queryset = annotate_assigned_reviews(queryset, event, user)
    if phase and phase.proposal_visibility == "assigned":
        return queryset.filter(is_assigned__gte=1)
    if reviewer_tracks := user.get_reviewer_tracks(event):
        queryset = queryset.filter(track__in=reviewer_tracks)
    return queryset


def submissions_for_user(event, user, review_context=False):
    """Return the submissions a user is allowed to see for this event.

    With ``review_context=True``, the queryset is narrowed to what the user
    can see *as a reviewer*: actual reviewer team members get
    ``submissions_for_reviewer`` applied (review phase, track restrictions,
    excluding own submissions), and pure orgas / admins still see everything
    except their own submissions.
    """
    if not user.is_anonymous:
        if is_only_reviewer(user, event):
            return submissions_for_reviewer(
                event.submissions.all(), event, user
            ).select_related("event", "track", "submission_type")
        if user.has_perm("submission.orga_list_submission", event):
            queryset = event.submissions.all()
            if review_context:
                if user in event.reviewers:
                    queryset = submissions_for_reviewer(queryset, event, user)
                else:
                    queryset = annotate_assigned_reviews(
                        queryset.exclude(speakers__user=user), event, user
                    )
            return queryset.select_related("event", "track", "submission_type")

    # Fall through: both anon users and authenticated users without
    # orga/reviewer permissions get here (e.g. speakers or attendees).
    if user.has_perm("schedule.list_schedule", event):
        return event.current_schedule.slots
    return event.submissions.none()


def reviewable_submissions_for_user(event, user):
    """Returns all submissions the user is permitted to review right now.

    Excludes submissions this user has submitted, and takes track team permissions,
    assignments and review phases into account. The result is ordered by review count.
    """
    queryset = submissions_for_user(event, user, review_context=True).filter(
        state=SubmissionStates.SUBMITTED
    )
    # Use a subquery instead of Count("reviews") to avoid a GROUP BY on the
    # outer query — this lets callers add order_by("?") without breaking the
    # annotation values (a known Django ORM issue with COUNT + RANDOM).
    review_count = (
        Review.objects.filter(submission=OuterRef("pk"))
        .order_by()
        .values("submission")
        .annotate(count=Count("pk"))
        .values("count")
    )
    queryset = queryset.annotate(
        review_count=Coalesce(Subquery(review_count), Value(0))
    )
    # Randomise within each priority tier so that "save and next" doesn't
    # always hand reviewers the same deterministic sequence of proposals.
    return queryset.order_by("-is_assigned", "review_count", "?")


def unreviewed_submissions_for_user(event, user):
    """Reviewable submissions that the user has not yet reviewed."""
    return reviewable_submissions_for_user(event, user).exclude(reviews__user=user)
