# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

import rules
from django.utils.timezone import now


@rules.predicate
def is_administrator(user, obj):
    return getattr(user, "is_administrator", False)


@rules.predicate
def is_reviewer(user, obj):
    event = getattr(obj, "event", None)
    if not user or user.is_anonymous or not obj or not event:
        return False
    # We’re not using get_permissions_for_event here, as this will always return
    # the full permission set for administrators, but we want to explicitly check
    # for team membership
    return user in event.reviewers


@rules.predicate
def is_only_reviewer(user, obj):
    """Check if the reviewer has submission permissions beyond their
    reviewer permissions. Ignores event settings permissions."""
    if not user or user.is_anonymous:
        return False
    permissions = user.get_permissions_for_event(obj.event)
    return "is_reviewer" in permissions and "can_change_submissions" not in permissions


@rules.predicate
def can_mark_speakers_arrived(user, obj):
    event = obj.event
    return (event.date_from - dt.timedelta(days=3)) <= now().date() <= event.date_to


@rules.predicate
def can_view_information(user, obj):
    from pretalx.submission.domain.queries.submission import (  # noqa: PLC0415 -- predicate
        information_for_user,
    )

    return information_for_user(obj.event, user).filter(pk=obj.pk).exists()
