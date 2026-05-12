# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms


def can_delete_track(track) -> bool:
    """True iff ``track`` is not referenced by any submission."""
    return not track.submissions.exists()
