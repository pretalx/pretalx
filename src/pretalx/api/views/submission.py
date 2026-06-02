# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Prefetch
from django.db.models.deletion import ProtectedError
from django.http import Http404
from django.utils.functional import cached_property
from rest_framework import serializers, status, viewsets
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.decorators import (
    action,
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from pretalx.api.documentation import (
    OpenApiResponse,
    build_expand_docs,
    build_search_docs,
    extend_schema,
    extend_schema_view,
)
from pretalx.api.filters.submission import SubmissionFilter
from pretalx.api.serializers.legacy import (
    LegacySubmissionOrgaSerializer,
    LegacySubmissionReviewerSerializer,
    LegacySubmissionSerializer,
)
from pretalx.api.serializers.submission import (
    AttendeeSignupSerializer,
    ResourceWriteSerializer,
    SubmissionOrgaSerializer,
    SubmissionReviewerSerializer,
    SubmissionSerializer,
    SubmissionTypeSerializer,
    TagSerializer,
    TrackSerializer,
)
from pretalx.api.versions import LEGACY
from pretalx.api.views.mixins import ActivityLogMixin, PretalxViewSetMixin
from pretalx.common.exceptions import SubmissionError
from pretalx.submission.domain.invitation import (
    retract_invitation as retract_invitation_domain,
)
from pretalx.submission.domain.invitation import send_invitation
from pretalx.submission.domain.queries.question import questions_for_user
from pretalx.submission.domain.queries.speaker import speakers_for_user
from pretalx.submission.domain.queries.submission import (
    annotate_submission_signup_status,
    signed_up_submission_codes,
    submissions_for_user,
)
from pretalx.submission.domain.resource import create_resource, delete_resource
from pretalx.submission.domain.submission import (
    delete_submission,
    invite_speaker,
    remove_speaker,
    set_submission_state,
)
from pretalx.submission.domain.submission_type import can_delete_submission_type
from pretalx.submission.domain.track import can_delete_track
from pretalx.submission.models import (
    Answer,
    Resource,
    Submission,
    SubmissionInvitation,
    SubmissionStates,
    SubmissionType,
    Tag,
    Track,
)
from pretalx.submission.validators.speaker import validate_invitation_target


class AddSpeakerSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    name = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    locale = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class RemoveSpeakerSerializer(serializers.Serializer):
    user = serializers.CharField(required=True)


@extend_schema_view(
    list=extend_schema(
        summary="List Submissions",
        parameters=[
            build_search_docs("title", "speaker.name"),
            build_expand_docs(
                "speakers",
                "speakers.answers",
                "track",
                "submission_type",
                "tags",
                "slots",
                "slots.room",
                "answers",
                "answers.question",
                "resources",
            ),
        ],
    ),
    retrieve=extend_schema(
        summary="Show Submission",
        parameters=[
            build_expand_docs(
                "speakers",
                "track",
                "submission_type",
                "tags",
                "slots",
                "slots.room",
                "answers",
                "resources",
            )
        ],
    ),
    create=extend_schema(
        summary="Create Submission",
        description="Note that a submission created via the API will start in the submitted state and without speakers. No notification emails will be sent, and the submission may be in an invalid state (e.g. if the event has required custom fields).",
        request=SubmissionOrgaSerializer,
        responses={200: SubmissionOrgaSerializer},
    ),
    update=extend_schema(
        summary="Update Submission",
        request=SubmissionOrgaSerializer,
        responses={200: SubmissionOrgaSerializer},
    ),
    partial_update=extend_schema(
        summary="Update Submission (Partial Update)",
        request=SubmissionOrgaSerializer,
        responses={200: SubmissionOrgaSerializer},
    ),
    destroy=extend_schema(
        summary="Delete Submission",
        description="This endpoint is only available to server administrators.",
    ),
    accept=extend_schema(summary="Accept Submission"),
    reject=extend_schema(summary="Reject Submission"),
    confirm=extend_schema(summary="Confirm Submission"),
    cancel=extend_schema(summary="Cancel Submission"),
    make_submitted=extend_schema(summary="Make Submission Submitted"),
    add_speaker=extend_schema(
        summary="Add Speaker to Submission",
        request=AddSpeakerSerializer,
        responses={200: SubmissionOrgaSerializer},
    ),
    remove_speaker=extend_schema(
        summary="Remove Speaker from Submission",
        request=RemoveSpeakerSerializer,
        responses={200: SubmissionOrgaSerializer},
    ),
    add_resource=extend_schema(
        summary="Add Resource to Submission",
        request=ResourceWriteSerializer,
        responses={200: SubmissionOrgaSerializer},
    ),
    remove_resource=extend_schema(
        summary="Remove Resource from Submission", responses={204: None}
    ),
    invite_speaker=extend_schema(
        summary="Invite Speaker to Submission",
        request=AddSpeakerSerializer,
        responses={200: SubmissionOrgaSerializer},
    ),
    retract_invitation=extend_schema(
        summary="Retract Speaker Invitation", responses={204: None}
    ),
    attendees=extend_schema(
        summary="List Attendee Signups",
        responses={200: AttendeeSignupSerializer(many=True)},
    ),
)
class SubmissionViewSet(ActivityLogMixin, PretalxViewSetMixin, viewsets.ModelViewSet):
    serializer_class = SubmissionSerializer
    queryset = Submission.objects.none()
    lookup_field = "code__iexact"
    search_fields = ("title", "speakers__name")
    filterset_class = SubmissionFilter
    ordering_fields = ("code", "title", "state", "created", "is_featured")
    ordering = ("code",)
    permission_map = {
        "make_submitted": "submission.state_change_submission",
        "accept": "submission.state_change_submission",
        "reject": "submission.state_change_submission",
        "confirm": "submission.state_change_submission",
        "cancel": "submission.state_change_submission",
        "add_speaker": "submission.update_submission",
        "remove_speaker": "submission.update_submission",
        "invite_speaker": "submission.update_submission",
        "retract_invitation": "submission.update_submission",
        "add_resource": "submission.update_submission",
        "remove_resource": "submission.update_submission",
        "attendees": "submission.orga_update_submission",
    }
    endpoint = "submissions"

    def get_legacy_queryset(self):
        base_qs = self.event.submissions.order_by("code")
        if not self.request.user.has_perm(
            "submission.orga_list_submission", self.event
        ):
            return base_qs.filter(
                pk__in=self.event.current_schedule.talks.filter(
                    is_visible=True
                ).values_list("submission_id", flat=True)
            )
        return base_qs

    def get_legacy_serializer_class(self):
        if self.request.user.has_perm("submission.orga_update_submission", self.event):
            return LegacySubmissionOrgaSerializer
        if self.request.user.has_perm("submission.orga_list_submission", self.event):
            return LegacySubmissionReviewerSerializer
        return LegacySubmissionSerializer

    def get_legacy_serializer(self, *args, **kwargs):
        serializer_questions = (self.request.query_params.get("questions") or "").split(
            ","
        )
        can_view_speakers = self.request.user.has_perm(
            "schedule.list_schedule", self.event
        ) or self.request.user.has_perm("person.orga_list_speakerprofile", self.event)
        if self.request.query_params.get("anon"):
            can_view_speakers = False
        return super().get_serializer(
            *args,
            can_view_speakers=can_view_speakers,
            event=self.event,
            questions=serializer_questions,
            **kwargs,
        )

    def get_serializer_class(self):
        if self.api_version == LEGACY:
            return self.get_legacy_serializer_class()
        return super().get_serializer_class()

    def get_unversioned_serializer_class(self):
        if self.can_change_submissions:
            return SubmissionOrgaSerializer
        if self.is_orga:
            return SubmissionReviewerSerializer
        return SubmissionSerializer

    @cached_property
    def is_orga(self):
        return self.event and self.request.user.has_perm(
            "submission.orga_list_submission", self.event
        )

    @cached_property
    def can_change_submissions(self):
        return self.event and self.request.user.has_perm(
            "submission.orga_update_submission", self.event
        )

    def get_serializer(self, *args, **kwargs):
        if self.api_version == LEGACY:
            return self.get_legacy_serializer(*args, **kwargs)
        return super().get_serializer(*args, **kwargs)

    @cached_property
    def speakers_for_user(self):
        if not self.event:
            return None
        return speakers_for_user(self.event, self.request.user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if not self.event:
            return context
        context["questions"] = questions_for_user(self.event, self.request.user)
        context["speakers"] = self.speakers_for_user
        context["schedule"] = self.event.current_schedule
        context["public_slots"] = not self.has_perm("delete")
        context["public_resources"] = not self.is_orga
        return context

    def get_queryset(self):
        if self.api_version == LEGACY:
            return self.get_legacy_queryset()
        if not self.event:
            # This is just during api doc creation
            return self.queryset

        speakers_qs = self.event.submitters.order_by("speaker_roles__position")
        if self.check_expanded_fields("speakers.user"):
            speakers_qs = speakers_qs.select_related("user")
        prefetches = [
            Prefetch("speakers", queryset=speakers_qs),
            Prefetch("answers", queryset=Answer.objects.select_related("question")),
            "slots",
            "tags",
            "resources",
        ]
        if self.can_change_submissions:
            prefetches += ["reviews", "assigned_reviewers", "invitations"]
        queryset = (
            submissions_for_user(self.event, self.request.user)
            .prefetch_related(*prefetches)
            .order_by("code")
        )
        if fields := self.check_expanded_fields(
            "answers.question",
            "answers.question.tracks",
            "answers.question.submission_types",
            "slots.room",
        ):
            queryset = queryset.prefetch_related(
                *[field.replace(".", "__") for field in fields]
            )
        if self.event.get_feature_flag("attendee_signup"):
            queryset = annotate_submission_signup_status(
                queryset, self.event.current_schedule
            )
        return queryset

    def perform_destroy(self, request, *args, **kwargs):
        delete_submission(self.get_object(), person=self.request.user, orga=True)

    def _set_state(self, new_state):
        submission = self.get_object()
        try:
            set_submission_state(
                submission, new_state, person=self.request.user, orga=True
            )
        except SubmissionError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(submission).data)

    @action(detail=True, methods=["POST"])
    def accept(self, request, **kwargs):
        return self._set_state(SubmissionStates.ACCEPTED)

    @action(detail=True, methods=["POST"])
    def reject(self, request, **kwargs):
        return self._set_state(SubmissionStates.REJECTED)

    @action(detail=True, methods=["POST"])
    def confirm(self, request, **kwargs):
        return self._set_state(SubmissionStates.CONFIRMED)

    @action(detail=True, methods=["POST"])
    def cancel(self, request, **kwargs):
        return self._set_state(SubmissionStates.CANCELED)

    @action(detail=True, methods=["POST"], url_path="make-submitted")
    def make_submitted(self, request, **kwargs):
        return self._set_state(SubmissionStates.SUBMITTED)

    @action(detail=True, methods=["POST"], url_path="add-speaker")
    def add_speaker(self, request, **kwargs):
        serializer = AddSpeakerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        submission = self.get_object()
        invite_speaker(
            submission,
            email=data["email"],
            name=data.get("name"),
            locale=data.get("locale"),
            user=self.request.user,
        )
        submission.refresh_from_db()
        return Response(SubmissionOrgaSerializer(submission).data)

    @action(detail=True, methods=["POST"], url_path="remove-speaker")
    def remove_speaker(self, request, **kwargs):
        serializer = RemoveSpeakerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submission = self.get_object()
        speaker = submission.speakers.filter(
            code=serializer.validated_data["user"]
        ).first()
        if not speaker:
            return Response(
                {"detail": "Speaker not found."}, status=status.HTTP_400_BAD_REQUEST
            )
        remove_speaker(submission, speaker, user=self.request.user)
        submission.refresh_from_db()
        return Response(SubmissionOrgaSerializer(submission).data)

    @action(detail=True, methods=["POST"], url_path="invitations")
    def invite_speaker(self, request, **kwargs):
        serializer = AddSpeakerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submission = self.get_object()
        email = serializer.validated_data["email"].lower()
        try:
            validate_invitation_target(submission, email)
        except DjangoValidationError as e:
            return Response(
                {"detail": e.messages[0]}, status=status.HTTP_400_BAD_REQUEST
            )

        send_invitation(submission, email=email, sender=request.user, orga=True)
        submission.refresh_from_db()
        return Response(SubmissionOrgaSerializer(submission).data)

    @action(
        detail=True,
        methods=["DELETE"],
        url_path=r"invitations/(?P<invitation_id>[0-9]+)",
    )
    def retract_invitation(self, request, invitation_id=None, **kwargs):
        submission = self.get_object()
        try:
            invitation = SubmissionInvitation.objects.get(
                pk=invitation_id, submission=submission
            )
        except SubmissionInvitation.DoesNotExist:
            return Response(
                {"detail": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND
            )

        retract_invitation_domain(invitation, person=request.user, orga=True)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["POST"], url_path="resources")
    @transaction.atomic
    def add_resource(self, request, **kwargs):
        submission = self.get_object()
        serializer = ResourceWriteSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        create_resource(submission, user=request.user, **serializer.validated_data)
        return Response(
            SubmissionOrgaSerializer(
                submission, context=self.get_serializer_context()
            ).data
        )

    @action(
        detail=True, methods=["DELETE"], url_path=r"resources/(?P<resource_id>[0-9]+)"
    )
    @transaction.atomic
    def remove_resource(self, request, resource_id=None, **kwargs):
        submission = self.get_object()
        try:
            resource = Resource.objects.get(pk=resource_id, submission=submission)
        except Resource.DoesNotExist:
            return Response(
                {"detail": "Resource not found."}, status=status.HTTP_404_NOT_FOUND
            )
        delete_resource(resource, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["GET"], url_path="attendees", pagination_class=None)
    def attendees(self, request, **kwargs):
        submission = self.get_object()
        if not submission.requires_signup:
            raise Http404
        signups = submission.attendee_signups.select_related(
            "attendee", "attendee__user"
        ).order_by("state", "position")
        return Response(AttendeeSignupSerializer(signups, many=True).data)


@extend_schema(
    summary="List favourite submissions",
    description="This endpoint is used by the schedule widget and uses session authentication.",
    responses={status.HTTP_200_OK: list[str]},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes((SessionAuthentication, TokenAuthentication))
def favourites_view(request, event):
    if not request.user.has_perm("schedule.list_schedule", request.event):
        raise PermissionDenied
    return Response(
        list(
            submissions_for_user(request.event, request.user)
            .filter(favourites__user=request.user)
            .values_list("code", flat=True)
        )
    )


@extend_schema(
    summary="List submissions the current user is signed up for",
    description="This endpoint is used by the schedule widget and uses session authentication.",
    responses={status.HTTP_200_OK: list[str]},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes((SessionAuthentication, TokenAuthentication))
def signups_view(request, event):
    if not request.user.has_perm("schedule.list_schedule", request.event):
        raise PermissionDenied
    return Response(sorted(signed_up_submission_codes(request.event, request.user)))


@extend_schema(
    summary="Add or remove a submission from favourites",
    description="This endpoint is used by the schedule widget and uses session authentication.",
    request=None,
    responses={
        status.HTTP_200_OK: {},
        status.HTTP_404_NOT_FOUND: OpenApiResponse(description="Submission not found."),
    },
)
@api_view(["POST", "DELETE"])
@permission_classes([IsAuthenticated])
@authentication_classes((SessionAuthentication, TokenAuthentication))
def favourite_view(request, event, code):
    if not request.user.has_perm("schedule.list_schedule", request.event):
        raise PermissionDenied
    submission = (
        submissions_for_user(request.event, request.user)
        .filter(code__iexact=code)
        .first()
    )
    if not submission:
        raise Http404

    if request.method == "POST":
        submission.add_favourite(request.user)
    else:
        submission.remove_favourite(request.user)
    return Response({})


@extend_schema_view(
    list=extend_schema(summary="List tags", parameters=[build_search_docs("tag")]),
    retrieve=extend_schema(summary="Show Tags"),
    create=extend_schema(summary="Create Tags"),
    update=extend_schema(summary="Update Tags"),
    partial_update=extend_schema(summary="Update Tags (Partial Update)"),
    destroy=extend_schema(summary="Delete Tags"),
)
class TagViewSet(ActivityLogMixin, PretalxViewSetMixin, viewsets.ModelViewSet):
    serializer_class = TagSerializer
    queryset = Tag.objects.none()
    endpoint = "tags"
    search_fields = ("tag",)
    ordering_fields = ("id", "tag")
    ordering = ("id",)

    def get_queryset(self):
        return self.event.tags.order_by("pk")


@extend_schema_view(
    list=extend_schema(
        summary="List Submission Types", parameters=[build_search_docs("name")]
    ),
    retrieve=extend_schema(summary="Show Submission Types"),
    create=extend_schema(summary="Create Submission Types"),
    update=extend_schema(summary="Update Submission Types"),
    partial_update=extend_schema(summary="Update Submission Types (Partial Update)"),
    destroy=extend_schema(summary="Delete Submission Types"),
)
class SubmissionTypeViewSet(
    ActivityLogMixin, PretalxViewSetMixin, viewsets.ModelViewSet
):
    serializer_class = SubmissionTypeSerializer
    queryset = SubmissionType.objects.none()
    endpoint = "submission-types"
    search_fields = ("name",)
    ordering_fields = ("id", "name", "default_duration")
    ordering = ("id",)

    def get_queryset(self):
        return self.event.submission_types.all()

    def perform_destroy(self, instance):
        if not can_delete_submission_type(instance):
            raise serializers.ValidationError(
                "This session type is in use in a proposal and cannot be deleted."
            )
        try:
            super().perform_destroy(instance)
        except ProtectedError as e:  # pragma: no cover -- race fallback
            raise serializers.ValidationError(
                "This session type is in use in a proposal and cannot be deleted."
            ) from e


@extend_schema_view(
    list=extend_schema(summary="List Tracks", parameters=[build_search_docs("name")]),
    retrieve=extend_schema(summary="Show Tracks"),
    create=extend_schema(summary="Create Tracks"),
    update=extend_schema(summary="Update Tracks"),
    partial_update=extend_schema(summary="Update Tracks (Partial Update)"),
    destroy=extend_schema(summary="Delete Tracks"),
)
class TrackViewSet(ActivityLogMixin, PretalxViewSetMixin, viewsets.ModelViewSet):
    serializer_class = TrackSerializer
    queryset = Track.objects.none()
    endpoint = "tracks"
    search_fields = ("name",)
    ordering_fields = ("id", "name")
    ordering = ("id",)

    def get_queryset(self):
        return self.event.tracks.all()

    def perform_destroy(self, instance):
        if not can_delete_track(instance):
            raise serializers.ValidationError(
                "This track is in use in a proposal and cannot be deleted."
            )
        try:
            super().perform_destroy(instance)
        except ProtectedError as e:  # pragma: no cover -- race fallback
            raise serializers.ValidationError(
                "This track is in use in a proposal and cannot be deleted."
            ) from e
