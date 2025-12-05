# SPDX-FileCopyrightText: 2025-present Florian Moesch
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from pretalx.api.filters.feedback import FeedbackFilter
from rest_framework import viewsets

from pretalx.api.documentation import extend_schema, extend_schema_view
from pretalx.api.serializers.feedback import FeedbackSerializer
from pretalx.api.views.mixins import ActivityLogMixin, PretalxViewSetMixin
from pretalx.submission.models import Feedback


@extend_schema_view(
    list=extend_schema(summary="List Feedbacks"),
    retrieve=extend_schema(summary="Show Feedback"),
    create=extend_schema(summary="Create Feedback"),
)
class FeedbackViewSet(ActivityLogMixin, PretalxViewSetMixin, viewsets.ModelViewSet):
    serializer_class = FeedbackSerializer
    queryset = Feedback.objects.none()
    filterset_class = FeedbackFilter
    ordering_fields = ("id", "created")
    ordering = ("id",)
    endpoint = "feedback"
    permission_map = {
        "list": "submission.list_feedback",
        "retrieve": "submission.view_feedback",
        "create": "submission.create_feedback",
    }

    def get_queryset(self):
        return (
            Feedback.objects.filter(talk__event=self.event)
            .all()
            .select_related("talk")
            .order_by("pk")
        )
