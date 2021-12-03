from rest_framework import viewsets

from pretalx.api.serializers.submission import (
    ScheduleListSerializer,
    ScheduleSerializer,
    SubmissionOrgaSerializer,
    SubmissionReviewerSerializer,
    SubmissionSerializer,
    TagSerializer,
)
from pretalx.schedule.models import Schedule
from pretalx.submission.models import Submission, Tag


class SubmissionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SubmissionSerializer
    queryset = Submission.objects.none()
    lookup_field = "code__iexact"
    filterset_fields = ("state", "content_locale", "submission_type")
    search_fields = ("title", "speakers__name")

    def get_queryset(self):
        if self.request._request.path.endswith(
            "/talks/"
        ) or not self.request.user.has_perm(
            "orga.view_submissions", self.request.event
        ):
            if (
                not self.request.user.has_perm(
                    "agenda.view_schedule", self.request.event
                )
                or not self.request.event.current_schedule
            ):
                return Submission.objects.none()
            return self.request.event.submissions.filter(
                pk__in=self.request.event.current_schedule.talks.filter(
                    is_visible=True
                ).values_list("submission_id", flat=True)
            )
        return self.request.event.submissions.all()

    def get_serializer_class(self):
        if self.request.user.has_perm("orga.change_submissions", self.request.event):
            return SubmissionOrgaSerializer
        if self.request.user.has_perm("orga.view_submissions", self.request.event):
            return SubmissionReviewerSerializer
        return SubmissionSerializer

    def get_serializer(self, *args, **kwargs):
        can_view_speakers = self.request.user.has_perm(
            "agenda.view_schedule", self.request.event
        ) or self.request.user.has_perm("orga.view_speakers", self.request.event)
        if self.request.query_params.get("anon"):
            can_view_speakers = False
        return super().get_serializer(
            *args,
            can_view_speakers=can_view_speakers,
            event=self.request.event,
            **kwargs
        )


class ScheduleViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ScheduleSerializer
    queryset = Schedule.objects.none()
    lookup_field = "version__iexact"

    def get_serializer_class(self):
        if self.action == "list":
            return ScheduleListSerializer
        return ScheduleSerializer  # self.action == 'retrieve'

    def get_object(self):
        try:
            return super().get_object()
        except Exception:
            is_public = (
                self.request.event.is_public
                and self.request.event.feature_flags["show_schedule"]
            )
            has_perm = self.request.user.has_perm(
                "orga.edit_schedule", self.request.event
            )
            query = self.kwargs.get(self.lookup_field)
            if has_perm and query == "wip":
                return self.request.event.wip_schedule
            if (
                (has_perm or is_public)
                and query == "latest"
                and self.request.event.current_schedule
            ):
                return self.request.event.current_schedule
            raise

    def get_queryset(self):
        qs = self.queryset
        is_public = (
            self.request.event.is_public
            and self.request.event.feature_flags["show_schedule"]
        )
        current_schedule = (
            self.request.event.current_schedule.pk
            if self.request.event.current_schedule
            else None
        )

        if self.request.user.has_perm("orga.view_schedule", self.request.event):
            return self.request.event.schedules.all()
        if is_public:
            return self.request.event.schedules.filter(pk=current_schedule)
        return qs


class TagViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TagSerializer
    queryset = Tag.objects.none()
    lookup_field = "tag__iexact"

    def get_queryset(self):
        if self.request.user.has_perm("orga.view_submissions", self.request.event):
            return self.request.event.tags.all()
        return Tag.objects.none()
