# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms


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


def event_reviewers(event):
    """Distinct users who hold reviewer access on ``event`` via any reviewer
    team. ``.distinct()`` is required because a user may belong to multiple
    reviewer teams on the same event.
    """
    from pretalx.person.models import User  # noqa: PLC0415 -- avoid circular import

    return User.objects.filter(teams__in=event_reviewer_teams(event)).distinct()
