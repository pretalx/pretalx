# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from pretalx.event.models import Event


def validate_event_slug_unique(slug, *, exclude_event=None):
    """Case-insensitive uniqueness for ``Event.slug``."""
    if not slug:
        return
    qs = Event.objects.filter(slug__iexact=slug)
    if exclude_event is not None:
        qs = qs.exclude(pk=exclude_event.pk)
    if qs.exists():
        raise ValidationError(
            {
                "slug": _(
                    "This short name is already taken, please choose another one (or ask the owner of that event to add you to their team)."
                )
            }
        )
