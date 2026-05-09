# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Q

from pretalx.event.models import Event


def events_for_user(user, queryset=None):
    """Events visible to ``user``: every public event plus ones the user has
    any team-granted permission on.

    ``queryset`` lets callers narrow the base set (e.g. to a single
    organiser) before the visibility filter is applied. Results are ordered
    newest first.
    """
    queryset = queryset if queryset is not None else Event.objects.all()
    if user.is_anonymous:
        queryset = queryset.filter(is_public=True)
    else:
        events = user.get_events_with_any_permission().values_list("pk", flat=True)
        queryset = queryset.filter(Q(is_public=True) | Q(pk__in=events))
    return queryset.order_by("-date_from")
