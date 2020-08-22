from django.template.defaultfilters import timeuntil
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext_lazy
from django.views.generic import TemplateView
from django_context_decorator import context
from django_scopes import scope

from pretalx.common.mixins.views import EventPermissionRequired, PermissionRequired
from pretalx.common.models.log import ActivityLog
from pretalx.event.models import Organiser
from pretalx.event.stages import get_stages
from pretalx.person.models import User
from pretalx.submission.models.submission import SubmissionStates


class DashboardEventListView(TemplateView):
    template_name = "orga/event_list.html"

    def event_info(self, event):
        with scope(event=event):
            event.is_open = event.cfp.is_open
            event.submission_count = event.submissions.count()
        return event

    def filter_event(self, event):
        query = self.request.GET.get("q")
        if not query:
            return True
        query = query.lower().strip()
        name = {"en": event.name} if isinstance(event.name, str) else event.name.data
        name = {"en": name} if isinstance(name, str) else name
        return query in event.slug or any(query in value for value in name.values())

    @context
    def current_orga_events(self):
        return [
            self.event_info(e)
            for e in self.request.orga_events
            if e.date_to >= now().date() and self.filter_event(e)
        ]

    @context
    def past_orga_events(self):
        return [
            self.event_info(e)
            for e in self.request.orga_events
            if e.date_to < now().date() and self.filter_event(e)
        ]


class DashboardOrganiserListView(PermissionRequired, TemplateView):
    template_name = "orga/organiser/list.html"
    permission_required = "orga.view_organisers"

    def filter_organiser(self, organiser, query):
        name = (
            {"en": organiser.name}
            if isinstance(organiser.name, str)
            else organiser.name.data
        )
        name = {"en": name} if isinstance(name, str) else name
        return query in organiser.slug or any(query in value for value in name.values())

    @context
    def organisers(self):
        if self.request.user.is_administrator:
            orgs = Organiser.objects.all()
        else:
            orgs = set(
                team.organiser
                for team in self.request.user.teams.filter(
                    can_change_organiser_settings=True
                )
            )
        query = self.request.GET.get("q")
        if not query:
            return orgs
        query = query.lower().strip()
        return [org for org in orgs if self.filter_organiser(org, query)]


class EventDashboardView(EventPermissionRequired, TemplateView):
    template_name = "orga/event/dashboard.html"
    permission_required = "orga.view_orga_area"

    def get_cfp_tiles(self, _now):
        result = []
        max_deadline = self.request.event.cfp.max_deadline
        if max_deadline and _now < max_deadline:
            result.append(
                {"large": timeuntil(max_deadline), "small": _("until the CfP ends")}
            )
        if self.request.event.cfp.is_open:
            result.append(
                {"url": self.request.event.cfp.urls.public, "large": _("Go to CfP")}
            )
        return result

    def get_review_tiles(self):
        result = []
        review_count = self.request.event.reviews.count()
        can_change_settings = self.request.user.has_perm(
            "orga.change_settings", self.request.event
        )
        if review_count:
            active_reviewers = (
                User.objects.filter(
                    teams__in=self.request.event.teams.filter(is_reviewer=True),
                    reviews__isnull=False,
                )
                .order_by("id")
                .distinct()
                .count()
            )
            result.append({"large": review_count, "small": _("Reviews")})
            result.append(
                {
                    "large": active_reviewers,
                    "small": _("Active reviewers"),
                    "url": self.request.event.organiser.orga_urls.teams
                    if can_change_settings
                    else None,
                }
            )
        return result

    @context
    def history(self):
        return ActivityLog.objects.filter(event=self.request.event)[:20]

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        event = self.request.event
        stages = get_stages(event)
        result["timeline"] = stages.values()
        result["go_to_target"] = (
            "schedule" if stages["REVIEW"]["phase"] == "done" else "cfp"
        )
        _now = now()
        today = _now.date()
        result["tiles"] = self.get_cfp_tiles(_now)
        if today < event.date_from:
            days = (event.date_from - today).days
            result["tiles"].append(
                {
                    "large": days,
                    "small": ngettext_lazy(
                        "day until event start", "days until event start", days
                    ),
                }
            )
        elif today > event.date_to:
            days = (today - event.date_from).days
            result["tiles"].append(
                {
                    "large": days,
                    "small": ngettext_lazy(
                        "day since event end", "days since event end", days
                    ),
                }
            )
        elif event.date_to != event.date_from:
            day = (today - event.date_from).days + 1
            result["tiles"].append(
                {
                    "large": _("Day {number}").format(number=day),
                    "small": _("of {total_days} days").format(
                        total_days=(event.date_to - event.date_from).days + 1
                    ),
                    "url": event.urls.schedule + f"#{today.isoformat()}",
                }
            )
        if event.current_schedule:
            result["tiles"].append(
                {
                    "large": event.current_schedule.version,
                    "small": _("current schedule"),
                    "url": event.urls.schedule,
                }
            )
        if event.submissions.count():
            count = event.submissions.count()
            result["tiles"].append(
                {
                    "large": count,
                    "small": ngettext_lazy("submission", "submissions", count),
                    "url": event.orga_urls.submissions,
                }
            )
            submitter_count = event.submitters.count()
            result["tiles"].append(
                {
                    "large": submitter_count,
                    "small": ngettext_lazy("submitter", "submitters", submitter_count),
                    "url": event.orga_urls.speakers,
                }
            )
            talk_count = event.talks.count()
            if talk_count:
                result["tiles"].append(
                    {
                        "large": talk_count,
                        "small": ngettext_lazy("talk", "talks", talk_count),
                        "url": event.orga_urls.submissions
                        + f"?state={SubmissionStates.ACCEPTED}&state={SubmissionStates.CONFIRMED}",
                    }
                )
                accepted_count = event.talks.filter(
                    state=SubmissionStates.ACCEPTED
                ).count()
                if accepted_count != 0:
                    result["tiles"].append(
                        {
                            "large": accepted_count,
                            "small": ngettext_lazy(
                                "unconfirmed talk", "unconfirmed talks", accepted_count
                            ),
                            "url": event.orga_urls.submissions
                            + f"?state={SubmissionStates.ACCEPTED}",
                        }
                    )
        count = event.speakers.count()
        if count:
            result["tiles"].append(
                {
                    "large": count,
                    "small": ngettext_lazy("speaker", "speakers", count),
                    "url": event.orga_urls.speakers + "?role=true",
                }
            )
        count = event.queued_mails.filter(sent__isnull=False).count()
        result["tiles"].append(
            {
                "large": count,
                "small": ngettext_lazy("sent email", "sent emails", count),
                "url": event.orga_urls.sent_mails,
            }
        )
        result["tiles"] += self.get_review_tiles()
        return result
