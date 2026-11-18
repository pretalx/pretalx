from collections import defaultdict

from django.http import Http404
from django.utils.functional import cached_property
from django.views.generic import TemplateView

from pretalx.common.views.mixins import PermissionRequired

from .colors import legend_and_colours
from .layout import Break, Session, layout_day

PLUGIN = "pretalx_track_schedule"
# The built-in schedule's permission (agenda/views/schedule.py, ScheduleView),
# checked against the same object, so this page is visible exactly when that
# one is
PERMISSION = "schedule.view_schedule"


def track_sort_key(track):
    return (track.position is None, track.position or 0, str(track.name))


def build_days(event, schedule):
    """([(date, DayLayout)], colour legend) for the published schedule, in the
    event timezone."""
    tz = event.tz
    sessions = defaultdict(list)
    breaks = defaultdict(list)
    # Load everything the page reads up front: newer pretalx (FETCH_MODE_RAISE
    # in debug) refuses lazy loading of related objects
    for slot in schedule.scheduled_talks.select_related("submission__track"):
        start, end = slot.start.astimezone(tz), slot.end.astimezone(tz)
        sessions[start.date()].append(
            Session(start=start, end=end, track=slot.submission.track, data=slot)
        )
    for slot in schedule.breaks:
        if not slot.start or not slot.end:
            continue
        start, end = slot.start.astimezone(tz), slot.end.astimezone(tz)
        breaks[start.date()].append(
            Break(
                start=start, end=end, description=str(slot.description or ""), data=slot
            )
        )
    # Colour by answer (e.g. difficulty), where set up; kept on the slot for
    # the template
    slots = [s.data for day in sessions.values() for s in day]
    legend, colours = legend_and_colours(event, [slot.submission_id for slot in slots])
    for slot in slots:
        slot.ts_label, slot.ts_color = colours.get(slot.submission_id, (None, None))
    track_order = sorted(
        {s.track for day in sessions.values() for s in day if s.track},
        key=track_sort_key,
    )
    days = [
        (day, layout_day(sessions[day], breaks[day], track_order))
        for day in sorted(set(sessions) | set(breaks))
    ]
    return days, legend


class TrackScheduleView(PermissionRequired, TemplateView):
    template_name = "pretalx_track_schedule/schedule.html"
    permission_required = PERMISSION

    def dispatch(self, request, *args, **kwargs):
        if PLUGIN not in request.event.plugin_list:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_object(self):
        # Like ScheduleView without a version: the current published schedule.
        # With none, the permission check fails and the page is a 404.
        schedule = self.request.event.current_schedule
        if schedule:
            schedule.event = self.request.event
        return schedule

    @cached_property
    def schedule(self):
        return self.object

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["schedule"] = self.schedule
        context["days"], context["legend"] = build_days(
            self.request.event, self.schedule
        )
        return context
