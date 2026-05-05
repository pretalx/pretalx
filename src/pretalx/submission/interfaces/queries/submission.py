# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Count, Exists, OuterRef, Prefetch, Q, Subquery, Value
from django.db.models.functions import Coalesce

from pretalx.person.models import SpeakerProfile
from pretalx.person.rules import is_only_reviewer
from pretalx.submission.enums import SubmissionStates


def sorted_speakers_prefetch(prefix=""):
    """Prefetch for speakers ordered by their speaking position.

    Use prefix="submission__" when prefetching from slot querysets.
    """
    lookup = f"{prefix}speakers" if prefix else "speakers"
    return Prefetch(
        lookup,
        queryset=SpeakerProfile.objects.select_related(
            "profile_picture", "event", "user"
        ).order_by("speaker_roles__position"),
    )


def filter_submissions_by_state(qs, state_filter):
    """Filter by an iterable of state values.

    Values prefixed with ``pending_state__`` (e.g. ``pending_state__accepted``)
    match against the ``pending_state`` column instead of ``state``; both kinds
    can be mixed and produce a disjunction.
    """
    states = [s for s in state_filter if not s.startswith("pending_state__")]
    pending = [
        s.removeprefix("pending_state__")
        for s in state_filter
        if s.startswith("pending_state__")
    ]
    if states and pending:
        return qs.filter(Q(state__in=states) | Q(pending_state__in=pending))
    if states:
        return qs.filter(state__in=states)
    if pending:
        return qs.filter(pending_state__in=pending)
    return qs


def search_submissions(qs, query, *, can_view_speakers, fulltext=False):
    """Free-text search over submissions.

    With ``can_view_speakers=False`` the search honours anonymisation: redacted
    fields are matched against the anonymised value instead of the original.
    With ``fulltext=True`` the search expands to abstract/description/notes/
    internal_notes in addition to the per-permission default fields.
    """
    if not query:
        return qs
    fields = ["code__icontains", "title__icontains"]
    if can_view_speakers:
        fields += ["speakers__user__name__icontains", "speakers__name__icontains"]
    if fulltext:
        fields += [
            "description__icontains",
            "abstract__icontains",
            "notes__icontains",
            "internal_notes__icontains",
        ]
    if can_view_speakers:
        return _plain_search(qs, query, fields)
    return _anonymised_search(qs, query, fields)


def _plain_search(qs, query, fields):
    filters = Q()
    for field in fields:
        filters |= Q(**{field: query})
    return qs.filter(filters)


def _anonymised_search(qs, query, fields):
    # Fields where the anonymised value should be searched instead of the
    # original when the reviewer cannot see speaker names.
    anonymisable = {"title", "description", "abstract", "notes"}
    redacted = Q(anonymised___anonymised=True)
    filters = Q()
    for field in fields:
        match = Q(**{field: query})
        base = field.split("__")[0]
        if base not in anonymisable:
            filters |= match
            continue
        # The original value matches unless this field was redacted; the
        # anonymised value is searched only when the field was redacted.
        filters |= match & (~redacted | ~Q(anonymised__has_key=base))
        filters |= redacted & Q(**{f"anonymised__{field}": query})
    return qs.filter(filters)


def submission_field_counts(qs, field):
    """Group ``qs`` by ``field`` and return ``{value: count}``.

    Used by filter facets to display per-bucket counts alongside choices.
    """
    return dict(qs.order_by(field).values_list(field).annotate(Count(field)))


def submission_state_facets(event, *, usable_states=None):
    """Counts of submissions per state plus per pending state.

    Returns ``{state_value: count, "pending_state__<value>": count}``.
    Both buckets honour ``usable_states`` so a "Pending accepted" total
    that included submissions in unrelated states would not mislead.
    """
    qs = event.submissions.all()
    if usable_states:
        qs = qs.filter(state__in=usable_states)
    counts = submission_field_counts(qs, "state")
    counts.update(
        {
            f"pending_state__{value}": count
            for value, count in submission_field_counts(
                qs.filter(pending_state__isnull=False), "pending_state"
            ).items()
        }
    )
    return counts


def tracks_with_submission_counts(event, queryset=None):
    """Annotate a track queryset with non-draft submission counts.

    Defaults to all of the event's tracks; pass ``queryset`` to narrow.
    Ordered descending by count so popular tracks lead the dropdown.
    """
    base = queryset if queryset is not None else event.tracks.all()
    return base.annotate(
        count=Count(
            "submissions",
            distinct=True,
            filter=Q(event=event) & ~Q(submissions__state=SubmissionStates.DRAFT),
        )
    ).order_by("-count")


def tags_with_submission_counts(event):
    """Annotate the event's tags with non-draft submission counts."""
    return event.tags.annotate(
        count=Count(
            "submissions",
            distinct=True,
            filter=~Q(submissions__state=SubmissionStates.DRAFT),
        )
    )


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
    from pretalx.submission.models import Review  # noqa: PLC0415 -- circular import

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
