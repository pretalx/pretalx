# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.submission.domain.submission import update_duration


def propagate_default_duration(submission_type):
    """Rewrite slot end-times for submissions that inherit
    ``submission_type.default_duration``. Call this after a save that
    actually changed the default duration; the function does not check.
    """
    for submission in submission_type.submissions.filter(duration__isnull=True):
        update_duration(submission)
