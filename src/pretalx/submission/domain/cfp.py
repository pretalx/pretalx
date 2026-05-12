# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from collections import defaultdict


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
