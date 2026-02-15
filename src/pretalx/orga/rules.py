# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import rules


@rules.predicate
def can_view_speaker_names(user, obj):
    """ONLY in use with users who don't have change permissions."""
    event = obj.event
    reviewer_teams = obj.event.teams.filter(members__in=[user], is_reviewer=True)
    if reviewer_teams and all(team.force_hide_speaker_names for team in reviewer_teams):
        return False
    return bool(
        event.active_review_phase and event.active_review_phase.can_see_speaker_names
    )


@rules.predicate
def orga_can_view_speakers(user, obj):
    event = getattr(obj, "event", None)
    if not user or user.is_anonymous or not obj or not event:
        return False
    if user.is_administrator:
        return True
    return "can_view_speakers" in user.get_permissions_for_event(event)
