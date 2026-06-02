# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import rules


@rules.predicate
def is_event_visible(user, event):
    return event and event.is_public


def check_team_permission(user, event, permission):
    # We could query for a matching team here, which would be more efficient
    # if we only ever wanted to know this. But realistically, there will be
    # more permission checks regarding the event permissions a user has,
    # and get_permissions_for_event is cached, so it is overall more efficient.
    return user.is_administrator or permission in user.get_permissions_for_event(event)


@rules.predicate
def can_change_event_settings(user, obj):
    event = getattr(obj, "event", None)
    if not event or not obj or not user or user.is_anonymous:
        return False
    return check_team_permission(user, event, "can_change_event_settings")


@rules.predicate
def can_change_teams(user, obj):
    from pretalx.event.domain.queries.team import (  # noqa: PLC0415 -- predicate
        user_teams_in_organiser,
    )

    if not user or user.is_anonymous:
        return False
    if user.is_administrator:
        return True
    if event := getattr(obj, "event", None):
        return check_team_permission(user, event, "can_change_teams")
    return user_teams_in_organiser(user, obj.organiser, can_change_teams=True).exists()


@rules.predicate
def can_change_organiser_settings(user, obj):
    from pretalx.event.domain.queries.team import (  # noqa: PLC0415 -- predicate
        user_teams_in_organiser,
    )

    event = getattr(obj, "event", None)
    if event:
        obj = event.organiser
    return (
        user.is_administrator
        or user_teams_in_organiser(
            user, obj, can_change_organiser_settings=True
        ).exists()
    )


@rules.predicate
def has_any_permission(user, obj):
    return bool(user.get_permissions_for_event(obj.event))


@rules.predicate
def has_any_organiser_permissions(user, obj):
    from pretalx.event.domain.queries.team import (  # noqa: PLC0415 -- predicate
        user_teams_in_organiser,
    )

    organiser = getattr(obj, "organiser", None) or obj
    return user.is_administrator or user_teams_in_organiser(user, organiser).exists()


@rules.predicate
def can_change_any_organiser_settings(user, obj):
    return (
        user.is_administrator
        or user.teams.filter(can_change_organiser_settings=True).exists()
    )


@rules.predicate
def can_create_events(user, obj):
    return user.is_administrator or user.teams.filter(can_create_events=True).exists()


@rules.predicate
def is_any_organiser(user, obj):
    return user.is_administrator or user.teams.exists()
