# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Q

from pretalx.event.models import Event


def speaker_access_events_for_user(*, user):
    """Events on which ``user`` may see speaker information across every
    organiser they have team membership on."""
    if user.is_administrator:
        return Event.objects.all()

    teams = user.teams.all()
    submission_q = Q(
        organiser_id__in=teams.filter(
            can_change_submissions=True, all_events=True
        ).values_list("organiser_id", flat=True)
    ) | Q(
        pk__in=teams.filter(can_change_submissions=True, all_events=False).values_list(
            "limit_events", flat=True
        )
    )

    # Reviewer access: a non-track-limited reviewer team that does not force
    # hide speaker names, on an event whose active review phase allows showing
    # speaker names. Mirrors person.orga_list_speakerprofile when its reviewer
    # branch is taken.
    reviewer_teams = teams.filter(
        is_reviewer=True,
        can_change_submissions=False,
        limit_tracks__isnull=True,
        force_hide_speaker_names=False,
    )
    reviewer_event_pks = Event.objects.filter(
        Q(
            organiser_id__in=reviewer_teams.filter(all_events=True).values_list(
                "organiser_id", flat=True
            )
        )
        | Q(
            pk__in=reviewer_teams.filter(all_events=False).values_list(
                "limit_events", flat=True
            )
        ),
        review_phases__is_active=True,
        review_phases__can_see_speaker_names=True,
    ).values("pk")

    return Event.objects.filter(submission_q | Q(pk__in=reviewer_event_pks)).distinct()


def user_teams_in_organiser(user, organiser, **filters):
    """The user's teams within ``organiser``, optionally narrowed by extra
    field filters (e.g. ``can_change_teams=True``).

    Used by predicates that need to look up team-granted permissions on an
    organiser without an event in scope, where the cached
    ``get_permissions_for_event`` does not apply.
    """
    return user.teams.filter(organiser=organiser, **filters)


def event_reviewer_teams(event):
    """The event's teams that grant reviewer access."""
    return event.teams.filter(is_reviewer=True)


def user_reviewer_teams_in_event(user, event):
    """The reviewer teams ``user`` belongs to for ``event``.

    Returns a queryset; callers can ``.exists()`` for a boolean check or
    iterate to inspect per-team flags such as ``force_hide_speaker_names``.
    """
    return event.teams.filter(members=user, is_reviewer=True)


def active_reviewers_for_event(event):
    """Reviewers on ``event`` who have submitted at least one review.

    ``.distinct()`` is required because a reviewer may belong to multiple
    reviewer teams on the same event.
    """
    return event.reviewers.filter(reviews__isnull=False).order_by("id").distinct()
