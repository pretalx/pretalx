# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.person.models import SpeakerProfile
from pretalx.submission.domain.queries.submission import submissions_for_user


def speakers_for_user(event, user, submissions=None):
    submissions = submissions or submissions_for_user(event, user)
    return (
        SpeakerProfile.objects.filter(event=event, submissions__in=submissions)
        .select_related("event", "user", "profile_picture", "user__profile_picture")
        .distinct()
    )
