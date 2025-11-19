# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db import transaction
from django.db.models.deletion import ProtectedError
from rest_framework import exceptions, viewsets

from pretalx.api.documentation import (
    build_expand_docs,
    build_search_docs,
    extend_schema,
    extend_schema_view,
)
from pretalx.api.serializers.access_code import SubmitterAccessCodeSerializer
from pretalx.api.views.mixins import PretalxViewSetMixin
from pretalx.submission.models import SubmitterAccessCode


@extend_schema_view(
    list=extend_schema(
        summary="List Access Codes",
        parameters=[
            build_search_docs("code"),
            build_expand_docs("track", "submission_type"),
        ],
    ),
    retrieve=extend_schema(
        summary="Show Access Code",
        parameters=[build_expand_docs("track", "submission_type")],
    ),
    create=extend_schema(summary="Create Access Code"),
    update=extend_schema(summary="Update Access Code"),
    partial_update=extend_schema(summary="Update Access Code (Partial Update)"),
    destroy=extend_schema(summary="Delete Access Code"),
)
class SubmitterAccessCodeViewSet(PretalxViewSetMixin, viewsets.ModelViewSet):
    serializer_class = SubmitterAccessCodeSerializer
    queryset = SubmitterAccessCode.objects.none()
    endpoint = "access-codes"
    search_fields = ("code",)
    ordering_fields = ("id", "code", "valid_until")
    ordering = ("id",)

    def get_queryset(self):
        queryset = (
            self.event.submitter_access_codes.all()
            .select_related("event")
            .order_by("pk")
        )
        if fields := self.check_expanded_fields("track", "submission_type"):
            queryset = queryset.select_related(*fields)
        return queryset

    def perform_destroy(self, instance):
        try:
            with transaction.atomic():
                instance.logged_actions().delete()
                return super().perform_destroy(instance)
        except ProtectedError:
            raise exceptions.ValidationError(
                "You cannot delete an access code that has been used already."
            )
