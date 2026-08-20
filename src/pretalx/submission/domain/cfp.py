# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from collections import defaultdict

from pretalx.submission.domain.submission import (
    available_submission_types_for_submitter,
    available_tracks_for_submitter,
)


def submission_types_by_deadline(event):
    deadlines = defaultdict(list)
    for submission_type in event.submission_types.filter(deadline__isnull=False):
        deadlines[submission_type.deadline].append(submission_type)
    return dict(deadlines)


def cfp_deadlines(event):
    deadlines = [
        (deadline.astimezone(event.tz), submission_type)
        for deadline, types in submission_types_by_deadline(event).items()
        for submission_type in types
    ]
    if event.cfp.deadline:
        deadlines.append((event.cfp.deadline.astimezone(event.tz), None))
    return deadlines


def access_code_blocker(event) -> str | None:
    submission_types, __ = available_submission_types_for_submitter(event)
    if not submission_types.exists():
        return "submission_type"
    if event.cfp.require_track and event.has_active_tracks:
        tracks, __ = available_tracks_for_submitter(event)
        if not tracks.exists():
            return "track"
    return None


def can_submit_without_access_code(event) -> bool:
    return access_code_blocker(event) is None
