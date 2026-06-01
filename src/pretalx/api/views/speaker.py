# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Prefetch
from django.utils.functional import cached_property
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, mixins, viewsets
from rest_framework.permissions import SAFE_METHODS

from pretalx.api.documentation import (
    build_expand_docs,
    build_search_docs,
    extend_schema,
    extend_schema_view,
)
from pretalx.api.serializers.legacy import (
    LegacySpeakerOrgaSerializer,
    LegacySpeakerReviewerSerializer,
    LegacySpeakerSerializer,
)
from pretalx.api.serializers.speaker import (
    SpeakerOrgaSerializer,
    SpeakerSerializer,
    SpeakerUpdateSerializer,
)
from pretalx.api.versions import LEGACY
from pretalx.api.views.mixins import PretalxViewSetMixin
from pretalx.person.models import SpeakerProfile
from pretalx.submission.domain.queries.question import questions_for_user
from pretalx.submission.domain.queries.speaker import speakers_for_user
from pretalx.submission.domain.queries.submission import submissions_for_user
from pretalx.submission.models import Answer


class SpeakerSearchFilter(filters.SearchFilter):
    def get_search_fields(self, view, request):
        if view.can_change_submissions:
            return ("name", "user__name", "user__email")
        return ("name", "user__name")


@extend_schema_view(
    list=extend_schema(
        summary="List Speakers",
        parameters=[
            build_search_docs(
                "name",
                extra_description="Organiser search also includes email addresses.",
            ),
            build_expand_docs("submissions", "answers", "answers.question"),
        ],
    ),
    retrieve=extend_schema(
        summary="Show Speaker",
        parameters=[build_expand_docs("submissions", "answers", "answers.question")],
    ),
    update=extend_schema(
        summary="Update Speaker",
        request=SpeakerUpdateSerializer,
        responses={200: SpeakerOrgaSerializer},
    ),
    partial_update=extend_schema(
        summary="Update Speaker (Partial Update)",
        request=SpeakerUpdateSerializer,
        responses={200: SpeakerOrgaSerializer},
    ),
)
class SpeakerViewSet(
    PretalxViewSetMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = SpeakerSerializer
    queryset = SpeakerProfile.objects.none()
    lookup_field = "code__iexact"
    ordering_fields = ("code", "name")
    ordering = ("code",)
    endpoint = "speakers"
    filter_backends = (SpeakerSearchFilter, DjangoFilterBackend)

    def get_legacy_serializer_class(self):
        if self.request.user.has_perm("submission.orga_update_submission", self.event):
            return LegacySpeakerOrgaSerializer
        if self.request.user.has_perm("person.orga_list_speakerprofile", self.event):
            return LegacySpeakerReviewerSerializer
        return LegacySpeakerSerializer

    def get_legacy_queryset(self):
        if self.request.user.has_perm("person.orga_list_speakerprofile", self.event):
            return self.event.submitters.order_by("code")
        if self.event.current_schedule and self.event.get_feature_flag("show_schedule"):
            return self.event.speakers.order_by("code")
        return SpeakerProfile.objects.none()

    def get_serializer(self, *args, **kwargs):
        if self.api_version == LEGACY:
            kwargs["questions"] = (
                self.request.query_params.get("questions") or ""
            ).split(",")
        return super().get_serializer(*args, **kwargs)

    @cached_property
    def can_change_submissions(self):
        return self.event and self.request.user.has_perm(
            "submission.orga_update_submission", self.event
        )

    def get_unversioned_serializer_class(self):
        if self.api_version == LEGACY:
            return self.get_legacy_serializer_class()
        if self.can_change_submissions:
            if self.request.method not in SAFE_METHODS:
                return SpeakerUpdateSerializer
            return SpeakerOrgaSerializer
        return SpeakerSerializer

    @cached_property
    def submissions_for_user(self):
        return submissions_for_user(self.event, self.request.user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if not self.event:
            return context
        context["questions"] = questions_for_user(self.event, self.request.user)
        # We don’t need to check for anonymisation here, because endpoint access implies
        # that the user isn’t restricted to anonymised content.
        context["submissions"] = self.submissions_for_user
        return context

    def get_queryset(self):
        if self.api_version == LEGACY:
            queryset = self.get_legacy_queryset() or self.queryset
            return queryset.select_related(
                "user", "event", "event__cfp", "profile_picture"
            )
        if not self.event:
            # This is just during api doc creation
            return self.queryset
        queryset = speakers_for_user(
            self.event,
            self.request.user,
            submissions=self.submissions_for_user,
            prefetch_submissions=True,
        ).prefetch_related(
            Prefetch("answers", queryset=Answer.objects.select_related("question"))
        )
        if fields := self.check_expanded_fields(
            "answers.question",
            "answers.question.tracks",
            "answers.question.submission_types",
            "submissions",
            "submissions.track",
            "submissions.submission_type",
        ):
            prefetches = [field.replace(".", "__") for field in fields]
            queryset = queryset.prefetch_related(*prefetches)
        return queryset
