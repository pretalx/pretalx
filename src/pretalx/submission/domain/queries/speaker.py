# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Prefetch, Q

from pretalx.person.enums import SpeakerProfileOrigin
from pretalx.person.models import SpeakerProfile
from pretalx.submission.domain.queries.submission import submissions_for_user


def speakers_for_user(
    event, user, submissions=None, prefetch_submissions=False, include_bare=False
):
    """Speaker profiles for event that user is allowed to see."""
    submissions = (
        submissions if submissions is not None else submissions_for_user(event, user)
    )
    visibility = Q(submissions__in=submissions)
    if include_bare:
        visibility |= ~Q(origin=SpeakerProfileOrigin.CFP)
    queryset = (
        SpeakerProfile.objects.filter(visibility, event=event)
        .select_related("event", "user", "profile_picture", "user__profile_picture")
        .distinct()
        .order_by("code")
    )
    if prefetch_submissions:
        queryset = queryset.prefetch_related(
            Prefetch("submissions", queryset=submissions.order_by("code"))
        )
    return queryset
