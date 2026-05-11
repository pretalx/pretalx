# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Prefetch

from pretalx.person.models import SpeakerProfile
from pretalx.submission.domain.queries.submission import submissions_for_user


def speakers_for_user(event, user, submissions=None, prefetch_submissions=False):
    """Speaker profiles for ``event`` that ``user`` is allowed to see.

    With ``prefetch_submissions=True`` the queryset also prefetches
    ``submissions`` against that same visibility.
    """
    submissions = (
        submissions if submissions is not None else submissions_for_user(event, user)
    )
    queryset = (
        SpeakerProfile.objects.filter(event=event, submissions__in=submissions)
        .select_related("event", "user", "profile_picture", "user__profile_picture")
        .distinct()
        .order_by("code")
    )
    if prefetch_submissions:
        queryset = queryset.prefetch_related(
            Prefetch("submissions", queryset=submissions.order_by("code"))
        )
    return queryset
