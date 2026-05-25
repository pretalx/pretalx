# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Count, Q
from django_scopes import scopes_disabled

from pretalx.person.models import SpeakerProfile
from pretalx.schedule.models import TalkSlot
from pretalx.submission.domain.queries.submission import (
    annotate_slot_signup_status,
    talks_for_event,
)
from pretalx.submission.models.submission import SubmissionStates


def other_speaker_profiles(speaker):
    """All :class:`SpeakerProfile` rows for the same user on different events."""
    with scopes_disabled():
        return SpeakerProfile.objects.filter(user_id=speaker.user_id).exclude(
            pk=speaker.pk
        )


def visible_talk_slots(speaker, schedule=None):
    """Visible talk slots for ``speaker`` in ``schedule`` (or the event's
    current schedule).

    Returns an empty queryset when no schedule exists. Speakers within each
    slot are pre-sorted by their position.
    """
    schedule = schedule or speaker.event.current_schedule
    if not schedule:
        return TalkSlot.objects.none()
    queryset = (
        schedule.talks.filter(submission__speakers=speaker, is_visible=True)
        .select_related(
            "submission",
            "room",
            "submission__event",
            "submission__track",
            "submission__submission_type",
        )
        .with_sorted_speakers()
    )
    if schedule.event.get_feature_flag("attendee_signup"):
        queryset = annotate_slot_signup_status(queryset)
    return queryset


def speakers_for_event(event):
    """Speakers visible in ``event``'s current released schedule.

    Follows ``talks_for_event`` to prevent diverging between public
    sessions and public speakers.
    """
    return (
        SpeakerProfile.objects.filter(submissions__in=talks_for_event(event))
        .select_related("event", "user", "profile_picture")
        .order_by("id")
        .distinct()
    )


def submitters_for_event(event):
    """Speakers who have any non-draft submission to ``event``."""
    return (
        SpeakerProfile.objects.filter(submissions__in=event.submissions.all())
        .select_related("event", "user", "profile_picture")
        .order_by("id")
        .distinct()
    )


def annotate_speaker_submission_counts(qs, *, event):
    """Annotate a SpeakerProfile queryset with submission_count and
    accepted_submission_count for ``event``."""
    event_filter = Q(submissions__event=event)
    return qs.annotate(
        submission_count=Count("submissions", filter=event_filter, distinct=True),
        accepted_submission_count=Count(
            "submissions",
            filter=event_filter
            & Q(submissions__state__in=SubmissionStates.accepted_states),
            distinct=True,
        ),
    )


def annotate_user_submission_counts(qs, *, events):
    """Annotate a User queryset with submission_count and
    accepted_submission_count, scoped to ``events`` via the user's profiles."""
    events_filter = Q(profiles__submissions__event__in=events)
    return qs.annotate(
        submission_count=Count(
            "profiles__submissions", filter=events_filter, distinct=True
        ),
        accepted_submission_count=Count(
            "profiles__submissions",
            filter=events_filter
            & Q(profiles__submissions__state__in=SubmissionStates.accepted_states),
            distinct=True,
        ),
    )


def filter_by_accepted_role(qs, role):
    """Filter speakers/users on the ``accepted_submission_count`` annotation.
    The caller must have annotated ``accepted_submission_count`` first (see
    ``annotate_speaker_submission_counts`` / ``annotate_user_submission_counts``).
    """
    if role == "speaker":
        return qs.filter(accepted_submission_count__gt=0)
    if role == "submitter":
        return qs.filter(accepted_submission_count=0)
    return qs
