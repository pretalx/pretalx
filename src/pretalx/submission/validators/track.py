# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_unique_track_name(track):
    """Reject duplicate ``Track.name`` within an event.

    Compares display strings rather than filtering on raw I18n JSON; see
    ``validate_unique_submission_type_name`` for the rationale.
    """
    if not (track.event_id and track.name):
        return
    name = str(track.name)
    siblings = track.event.tracks.exclude(pk=track.pk)
    if any(str(other.name) == name for other in siblings):
        raise ValidationError({"name": _("You already have a track by this name!")})
