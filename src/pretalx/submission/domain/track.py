# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.submission.domain.submission import pin_signup_required


def can_delete_track(track) -> bool:
    """True iff ``track`` is not referenced by any submission."""
    return not track.submissions.exists()


def apply_track_field_changes(track, changed_fields):
    if (
        "attendee_signup_required" in changed_fields
        and track.attendee_signup_required is False
    ):
        return pin_signup_required(track.submissions.all())
    return []
