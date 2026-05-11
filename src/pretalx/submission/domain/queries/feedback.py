# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Q


def feedback_for_speaker(submission, user):
    """Feedback on ``submission`` that ``user`` is allowed to see as a speaker.

    A speaker sees feedback directed specifically at them, plus general
    feedback that wasn't routed to any particular speaker. Feedback aimed at
    co-speakers is intentionally hidden.
    """
    return submission.feedback.filter(
        Q(speaker__user=user) | Q(speaker__isnull=True)
    ).select_related("speaker")
