# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import socket
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_event_slug_unique(slug, *, exclude_event=None):
    """Case-insensitive uniqueness for ``Event.slug``."""
    if not slug:
        return

    from pretalx.event.models import Event  # noqa: PLC0415 -- predicate

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


def normalize_custom_domain(value):
    if not value:
        return value
    value = value.lower()
    if not value.startswith("https://"):
        value = value.removeprefix("http://")
        value = "https://" + value
    return value.rstrip("/")


def validate_custom_domain(value):
    if not value:
        return value
    value_netloc = value[len("https://") :]
    site_netloc = urlparse(settings.SITE_URL).netloc.lower()
    if value_netloc == site_netloc:
        raise ValidationError(
            _("Please do not choose the default domain as custom event domain.")
        )
    try:
        socket.gethostbyname(value_netloc)
    except OSError:
        raise ValidationError(
            _(
                "The domain “{domain}” does not have a name server entry at this time. Please make sure the domain is working before configuring it here."
            ).format(domain=value)
        ) from None
    return value
