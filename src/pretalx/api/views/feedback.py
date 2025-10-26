# SPDX-FileCopyrightText: 2025-present Florian Moesch
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets

from pretalx.api.mixins import PretalxViewSetMixin
from pretalx.api.serializers.feedback import FeedbackSerializer
from pretalx.submission.models import Feedback


@extend_schema_view(
    list=extend_schema(
        summary="List Feedback",
    ),
    retrieve=extend_schema(
        summary="Show Feedback",
    ),
    create=extend_schema(summary="Create Feedback"),
)
class FeedbackViewSet(PretalxViewSetMixin, viewsets.ModelViewSet):
    serializer_class = FeedbackSerializer
    queryset = Feedback.objects.none()
    endpoint = "feedback"
    ordering = ("id",)
    permission_map = {
        "list": "submission.list_feedback",
        "retrieve": "submission.view_feedback",
        "create": "submission.create_feedback",
    }
    search_fields = ("talk__code__iexact", "speaker__name")

    def get_queryset(self):
        queryset = (
            Feedback.objects.filter(talk__event=self.event)
            .all()
            .select_related("talk")
            .order_by("pk")
        )
        return queryset
