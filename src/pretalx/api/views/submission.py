from rest_framework import viewsets

from pretalx.api.serializers.submission import (
    ScheduleSerializer, SubmissionSerializer,
)
from pretalx.schedule.models import Schedule
from pretalx.submission.models import Submission


class SubmissionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SubmissionSerializer
    queryset = Submission.objects.none()
    lookup_field = 'code__iexact'
    filter_fields = ('state', 'content_locale', 'submission_type')
    search_fields = ('title', 'speakers__name')

    def get_base_queryset(self):
        if self.request.user.has_perm('orga.view_submissions', self.request.event):
            return self.request.event.submissions.all()
        if self.request.event.current_schedule and self.request.event.settings.show_schedule:
            return self.request.event.submissions.filter(slots__in=self.request.event.current_schedule.talks.all())

    def get_queryset(self):
        qs = self.get_base_queryset() or self.queryset
        if 'talks' in self.request._request.path:
            qs = qs.filter(slots__schedule=self.request.event.current_schedule)
        return qs


class ScheduleViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ScheduleSerializer
    queryset = Schedule.objects.none()

    def get_queryset(self):
        qs = self.queryset
        is_public = self.request.event.is_public and self.request.event.settings.show_schedule
        current_schedule = self.request.event.current_schedule.pk if self.request.event.current_schedule else None
        wip_schedule = self.request.event.wip_schedule.pk if self.request.event.wip_schedule else None

        if self.request.user.has_perm('orga.view_schedule', self.request.event):
            return self.request.event.schedules.filter(pk__in=[current_schedule, wip_schedule])
        if is_public:
            return self.request.event.schedules.filter(pk=current_schedule)
        return qs
