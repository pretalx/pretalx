# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Q

from pretalx.event.models import Event


def events_for_user(user, queryset=None):
    """Events visible to ``user``."""
    queryset = queryset if queryset is not None else Event.objects.all()
    if user.is_anonymous:
        queryset = queryset.filter(is_public=True)
    else:
        events = user.get_events_with_any_permission().values_list("pk", flat=True)
        queryset = queryset.filter(Q(is_public=True) | Q(pk__in=events))
    return queryset.order_by("-date_from")


def events_for_custom_domain(scheme, host, domain=None):
    """Events whose ``custom_domain`` is set to ``scheme://host``,
    or to ``domain`` (which happens when ``host`` includes a port).
    """
    q = Q(custom_domain=f"{scheme}://{host}")
    if domain and domain != host:
        q |= Q(custom_domain=f"{scheme}://{domain}")
    return Event.objects.filter(q).order_by("-date_from")


def speaker_events_for_user(user):
    """Events on which ``user`` is a submitter on at least one submission."""
    return (
        Event.objects.filter(submissions__speakers__user=user)
        .distinct()
        .order_by("-date_from")
    )
