# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Q
from rest_framework import permissions, viewsets

from pretalx.api.documentation import (
    build_search_docs,
    extend_schema,
    extend_schema_view,
)
from pretalx.api.serializers.event import EventListSerializer, EventSerializer
from pretalx.api.views.mixins import PretalxViewSetMixin
from pretalx.event.domain.queries.event import events_for_user
from pretalx.event.models import Event


@extend_schema_view(
    list=extend_schema(
        summary="List Events", parameters=[build_search_docs("name")], tags=["events"]
    ),
    retrieve=extend_schema(summary="Show Events", tags=["events"]),
)
class EventViewSet(PretalxViewSetMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = EventSerializer
    queryset = Event.objects.none()
    lookup_field = "slug"
    lookup_url_kwarg = "event"
    pagination_class = None
    permission_classes = [permissions.AllowAny]
    search_fields = ("name",)
    filterset_fields = ("is_public",)
    ordering_fields = ("date_from", "date_to", "name", "slug")
    ordering = ("-date_from",)

    def get_unversioned_serializer_class(self):
        if self.action == "list":
            return EventListSerializer
        return EventSerializer

    def get_queryset(self):
        queryset = events_for_user(self.request.user)
        if token := getattr(self.request, "auth", None):
            # A token scoped to a subset of events must not reveal even the
            # metadata of the user's other (non-public) events. Public events
            # stay visible, since they are discoverable by anyone anyway.
            queryset = queryset.filter(Q(is_public=True) | Q(pk__in=token.events.all()))
        return queryset.order_by("-date_from")
