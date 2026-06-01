# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import (
    BooleanField,
    Case,
    CharField,
    Count,
    Exists,
    F,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce

from pretalx.person.models import SpeakerInformation, SpeakerProfile
from pretalx.person.rules import is_only_reviewer
from pretalx.schedule.models.slot import TalkSlot
from pretalx.submission.domain.queries.review import annotate_review_count
from pretalx.submission.enums import (
    AttendeeSignupStates,
    SignupStatus,
    SubmissionStates,
)


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


# ``set_submission_state`` clears ``is_featured`` on transitions into these
# states, but the orga ``ToggleFeatured`` view and the orga submission form
# can both flip ``is_featured`` directly without touching ``state`` — so the
# pairing is enforced here.
FEATURED_HIDDEN_STATES = (
    SubmissionStates.REJECTED,
    SubmissionStates.CANCELED,
    SubmissionStates.WITHDRAWN,
)


def featured_submissions(event):
    """Render queryset for the public featured-sessions page of ``event``."""
    return (
        event.submissions.filter(is_featured=True)
        .exclude(state__in=FEATURED_HIDDEN_STATES)
        .select_related("event", "submission_type")
        .with_sorted_speakers()
        .order_by("title")
    )


def has_featured_submissions(event):
    """Cheap existence check: does ``event`` have any visible featured rows?"""
    return (
        event.submissions.filter(is_featured=True)
        .exclude(state__in=FEATURED_HIDDEN_STATES)
        .exists()
    )


def talks_for_event(event):
    """Submissions that have a slot in ``event``'s current released schedule.

    Returns an empty queryset before the first schedule release.
    """
    if event.current_schedule:
        return (
            event.submissions.filter(slots__in=event.current_schedule.scheduled_talks)
            .select_related("submission_type")
            .with_sorted_speakers()
        )
    return event.submissions.none()


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


def annotate_requires_signup(queryset, target=None):
    if "_annotated_requires_signup" in queryset.query.annotations:
        return queryset
    prefix = f"{target}__" if target else ""
    return queryset.annotate(
        _annotated_requires_signup=Case(
            When(**{f"{prefix}attendee_signup_required": True}, then=Value(True)),
            When(**{f"{prefix}attendee_signup_required": False}, then=Value(False)),
            When(
                **{f"{prefix}track__attendee_signup_required": True}, then=Value(True)
            ),
            When(
                **{f"{prefix}submission_type__attendee_signup_required": True},
                then=Value(True),
            ),
            default=Value(False),
            output_field=BooleanField(),
        )
    )


def annotate_slot_requires_signup(slot_queryset):
    return annotate_requires_signup(slot_queryset, target="submission")


def annotate_confirmed_signup_count(queryset, target=None):
    if "_annotated_confirmed_signup_count" in queryset.query.annotations:
        return queryset
    prefix = f"{target}__" if target else ""
    relation = f"{prefix}attendee_signups"
    return queryset.annotate(
        _annotated_confirmed_signup_count=Count(
            relation,
            filter=Q(**{f"{relation}__state": AttendeeSignupStates.CONFIRMED}),
            distinct=True,
        )
    )


def annotate_slot_confirmed_signup_count(slot_queryset):
    return annotate_confirmed_signup_count(slot_queryset, target="submission")


def _signup_status_case():
    """Used to annotate signup status on slot or submission qs."""
    return Case(
        When(_annotated_requires_signup=False, then=Value(None)),
        When(
            _annotated_signup_capacity__isnull=False,
            _annotated_confirmed_signup_count__gte=F("_annotated_signup_capacity"),
            then=Value(SignupStatus.FULL),
        ),
        default=Value(SignupStatus.OPEN),
        output_field=CharField(null=True),
    )


def annotate_slot_signup_status(slot_queryset):
    if "_annotated_signup_status" in slot_queryset.query.annotations:
        return slot_queryset
    slot_queryset = annotate_slot_requires_signup(slot_queryset)
    slot_queryset = annotate_slot_confirmed_signup_count(slot_queryset)
    slot_queryset = slot_queryset.annotate(
        _annotated_signup_capacity=Coalesce(
            "submission__attendee_signup_capacity", "room__capacity"
        )
    )
    return slot_queryset.annotate(_annotated_signup_status=_signup_status_case())


def annotate_submission_signup_status(queryset, current_schedule):
    if "_annotated_signup_status" in queryset.query.annotations:
        return queryset
    queryset = annotate_requires_signup(queryset)
    queryset = annotate_confirmed_signup_count(queryset)
    if current_schedule is not None:
        room_capacity = (
            TalkSlot.objects.filter(
                submission=OuterRef("pk"), schedule=current_schedule
            )
            .order_by("pk")
            .values("room__capacity")[:1]
        )
        queryset = queryset.annotate(
            _annotated_signup_capacity=Coalesce(
                "attendee_signup_capacity", Subquery(room_capacity)
            )
        )
    else:
        queryset = queryset.annotate(
            _annotated_signup_capacity=F("attendee_signup_capacity")
        )
    return queryset.annotate(_annotated_signup_status=_signup_status_case())


def annotate_submission_count(queryset):
    return queryset.annotate(
        submission_count=Count(
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
    if user.is_anonymous or "is_reviewer" not in user.get_permissions_for_event(event):
        return event.submissions.none()
    if not (phase := event.active_review_phase):
        queryset = event.submissions.none()
    queryset = queryset.exclude(speakers__user=user)
    queryset = annotate_assigned_reviews(queryset, event, user)
    if phase and phase.proposal_visibility == "assigned":
        return queryset.filter(is_assigned__gte=1)
    reviewer_tracks = user.get_reviewer_tracks(event)
    if reviewer_tracks is not None:
        queryset = queryset.filter(track__in=reviewer_tracks)
    return queryset


def submissions_for_user(event, user, review_context=False):
    """Return the ``Submission`` queryset a user may see for this event.

    Always returns a ``Submission`` queryset:

    - reviewers without submission-change access AND users with more
      access when review_context=True: ``submissions_for_reviewer``
    - orgas / admins get every submission otherwise
    - everyone else (anonymous users, speakers, attendees) gets the
      released-schedule submissions if they may see the public schedule
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

    # Fall through: anon users and authenticated users without
    # orga/reviewer permissions (e.g. speakers or attendees).
    if user.has_perm("schedule.list_schedule", event) and event.current_schedule:
        return event.current_schedule.slots
    return event.submissions.none()


def signed_up_submissions_for_user(event, user):
    if user.is_anonymous:
        return event.submissions.none()
    return submissions_for_user(event, user).filter(
        attendee_signups__attendee__user=user,
        attendee_signups__state=AttendeeSignupStates.CONFIRMED,
    )


def signed_up_submission_codes(event, user):
    if user.is_anonymous:
        return set()
    return set(
        signed_up_submissions_for_user(event, user)
        .values_list("code", flat=True)
        .distinct()
    )


def reviewable_submissions_for_user(event, user):
    """Returns all submissions the user is permitted to review right now.

    Excludes submissions this user has submitted, and takes track team permissions,
    assignments and review phases into account. The result is ordered by review count.
    """
    queryset = submissions_for_user(event, user, review_context=True).filter(
        state=SubmissionStates.SUBMITTED
    )
    queryset = annotate_review_count(queryset)
    # Randomise within each priority tier so that "save and next" doesn't
    # always hand reviewers the same deterministic sequence of proposals.
    return queryset.order_by("-is_assigned", "review_count", "?")


def unreviewed_submissions_for_user(event, user):
    """Reviewable submissions that the user has not yet reviewed."""
    return reviewable_submissions_for_user(event, user).exclude(reviews__user=user)


def information_for_user(event, user):
    """Return the SpeakerInformation entries this user is allowed to see.

    A user can see an information item when they have a submission on the
    event whose track, submission type, and state match the item's filters
    and target group. Items with empty ``limit_tracks`` / ``limit_types``
    impose no constraint on those axes.
    """
    if not user or user.is_anonymous:
        return event.information.none()

    track_links = SpeakerInformation.limit_tracks.through.objects.filter(
        speakerinformation_id=OuterRef(OuterRef("pk"))
    )
    type_links = SpeakerInformation.limit_types.through.objects.filter(
        speakerinformation_id=OuterRef(OuterRef("pk"))
    )

    user_subs = (
        event.submissions.filter(speakers__user=user)
        .filter(Q(track__in=track_links.values("track_id")) | ~Exists(track_links))
        .filter(
            Q(submission_type__in=type_links.values("submissiontype_id"))
            | ~Exists(type_links)
        )
    )

    return event.information.alias(
        _has_submitter=Exists(user_subs),
        _has_confirmed=Exists(user_subs.filter(state=SubmissionStates.CONFIRMED)),
        _has_accepted=Exists(
            user_subs.filter(state__in=list(SubmissionStates.accepted_states))
        ),
    ).filter(
        Q(target_group="submitters", _has_submitter=True)
        | Q(target_group="confirmed", _has_confirmed=True)
        | Q(target_group="accepted", _has_accepted=True)
    )
