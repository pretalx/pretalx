# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import models
from django.db.models import OuterRef, Subquery

from pretalx.person.models import SpeakerProfile, User
from pretalx.submission.models import Submission


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


def with_speaker_code(qs, event):
    profiles = SpeakerProfile.objects.filter(user_id=OuterRef("pk"), event=event)
    return qs.annotate(
        speaker_code=Subquery(
            profiles.filter(submissions__isnull=False).values("code")[:1]
        ),
        speaker_name=Subquery(profiles.values("name")[:1]),
    )


def submitter_users_for_events(events):
    return User.objects.filter(
        profiles__in=SpeakerProfile.objects.filter(
            submissions__in=Submission.objects.filter(event__in=events)
        )
    ).distinct()
