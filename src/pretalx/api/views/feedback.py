# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from rest_framework import exceptions, mixins, viewsets
from rest_framework.permissions import AllowAny

from pretalx.api.documentation import (
    build_expand_docs,
    build_search_docs,
    extend_schema,
    extend_schema_view,
)
from pretalx.api.filters.feedback import FeedbackFilter
from pretalx.api.serializers.feedback import FeedbackSerializer, FeedbackWriteSerializer
from pretalx.api.views.mixins import PretalxViewSetMixin
from pretalx.submission.models import Feedback


@extend_schema_view(
    list=extend_schema(
        summary="List Feedback",
        parameters=[
            build_search_docs("submission.title"),
            build_expand_docs("submission", "speaker"),
        ],
    ),
    retrieve=extend_schema(
        summary="Show Feedback", parameters=[build_expand_docs("submission", "speaker")]
    ),
    create=extend_schema(
        summary="Create Feedback",
        description="Submit feedback for a session. This endpoint is publicly accessible.",
        request=FeedbackWriteSerializer,
        responses={201: FeedbackSerializer},
    ),
    destroy=extend_schema(summary="Delete Feedback"),
)
class FeedbackViewSet(
    PretalxViewSetMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = FeedbackSerializer
    queryset = Feedback.objects.none()
    search_fields = ("talk__title",)
    filterset_class = FeedbackFilter
    ordering_fields = ("id", "created")
    ordering = ("id",)
    endpoint = "feedback"

    def get_permissions(self):
        if self.action == "create":
            return [AllowAny()]
        return super().get_permissions()

    def get_unversioned_serializer_class(self):
        if self.action == "create":
            return FeedbackWriteSerializer
        return FeedbackSerializer

    def get_queryset(self):
        if self.request.user.is_anonymous:
            return Feedback.objects.none()

        queryset = Feedback.objects.filter(talk__event=self.event).select_related(
            "talk", "speaker"
        )
        if fields := self.check_expanded_fields(
            "submission.track", "submission.submission_type"
        ):
            queryset = queryset.select_related(
                *[field.replace("submission.", "talk__", 1) for field in fields]
            )
        return queryset

    def create(self, request, *args, **kwargs):
        if not self.event.get_feature_flag("use_feedback"):
            raise exceptions.PermissionDenied("Feedback is not enabled for this event.")
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        # Don't log action for anonymous feedback creation
        serializer.save()
