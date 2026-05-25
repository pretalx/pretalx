# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import logging
import socket

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_domain_name
from django.utils.translation import gettext_lazy as _

from pretalx.common.text.phrases import phrases

logger = logging.getLogger(__name__)


def validate_feature_flags(value):
    if not isinstance(value, dict):
        return
    if value.get("attendee_signup") and value.get("present_multiple_times"):
        raise ValidationError(
            phrases.orga.signup_multi_slot_conflict, code="signup_multi_slot_conflict"
        )


def validate_attendee_signup_settings(value):
    if value is None:
        return
    if not isinstance(value, dict):
        raise ValidationError(
            "Attendee signup settings must be a dictionary.", code="not_dict"
        )
    domains = value.get("signup_domains") or []
    if not isinstance(domains, list):
        raise ValidationError(
            "signup_domains must be a list of domain strings.", code="domains_not_list"
        )
    for domain in domains:
        validate_domain_name(domain)


def validate_event_slug_unique(slug, *, exclude_event=None):
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


def _resolve_host(host):
    """Return ``(canonical_name, {ip, ...})`` for ``host``.

    Resolution follows the CNAME chain and covers v4 and v6.
    """
    infos = socket.getaddrinfo(
        host, None, type=socket.SOCK_STREAM, flags=socket.AI_CANONNAME
    )
    canonical = host
    ips = set()
    for _family, _type, _proto, canonname, sockaddr in infos:
        if canonname:
            canonical = canonname
        ips.add(sockaddr[0])
    return canonical.rstrip(".").lower(), ips


def validate_custom_domain(value):
    """Custom domain MUST resolve and not be the default domain.

    Returns ``(value, resolution)`` where ``resolution`` is the
    ``(canonical_name, {ip, ...})`` tuple for the custom host (or ``None``
    for an empty value) so we can re-use the resolution for
    :func:`custom_domain_points_to_site` instead of re-running DNS.
    """
    if not value:
        return value, None
    custom_host = value[len("https://") :].split(":")[0]
    if custom_host == settings.SITE_HOST:
        raise ValidationError(
            _("Please do not choose the default domain as custom event domain.")
        )
    try:
        resolution = _resolve_host(custom_host)
    except OSError:
        raise ValidationError(
            _(
                "The domain “{domain}” does not have a name server entry at this time. Please make sure the domain is working before configuring it here."
            ).format(domain=value)
        ) from None
    return value, resolution


def custom_domain_points_to_site(value, custom_resolution=None):
    """The custom domain SHOULD resolve to the main site.

    DNS is complex, so we can’t block on this, but we can show a
    warning when an organiser changes their domain and the value
    does not look right. Supports CNAME.
    """
    if not value:
        return True
    site_host = settings.SITE_HOST
    if not site_host:
        return True
    if custom_resolution is None:
        custom_host = value[len("https://") :].split(":")[0]
        try:
            custom_resolution = _resolve_host(custom_host)
        except OSError:
            # Unresolvable custom domains are already hard-rejected by
            # validate_custom_domain; nothing to warn about here.
            return True
    custom_canonical, custom_ips = custom_resolution
    try:
        site_canonical, site_ips = _resolve_host(site_host)
    except OSError:
        logger.warning(
            "Cannot resolve own site host %r; skipping the custom domain "
            "pointing check for %r. Domain verification is inert until the "
            "site host resolves.",
            site_host,
            value,
        )
        return True
    return custom_canonical == site_canonical or bool(custom_ips & site_ips)
