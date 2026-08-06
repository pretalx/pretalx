# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import models

from pretalx.person.models import SpeakerProfile


def with_profiles(qs, event):
    """Prefetch the user's :class:`SpeakerProfile` for ``event`` onto
    ``_speakers`` so :meth:`User.get_speaker` can hit the cache."""
    return qs.prefetch_related(
        models.Prefetch(
            "profiles",
            queryset=SpeakerProfile.objects.filter(event=event).select_related("event"),
            to_attr="_speakers",
        )
    ).distinct()
