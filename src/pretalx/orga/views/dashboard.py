# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: Florian Mösch
# SPDX-FileContributor: luto

from django.db.models import Q
from django.shortcuts import redirect
from django.template.defaultfilters import timeuntil
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext_lazy
from django.views.generic import TemplateView
from django_context_decorator import context
from django_scopes import scopes_disabled

from pretalx.common.domain.queries.log import event_activity_log
from pretalx.common.log import group_activity_log
from pretalx.common.views.mixins import EventPermissionRequired, PermissionRequired
from pretalx.event.domain.queries.event import speaker_events_for_user
from pretalx.event.domain.queries.organiser import organisers_for_user
from pretalx.event.domain.queries.team import (
    active_reviewers_for_event,
    user_reviewer_teams_in_event,
)
from pretalx.event.models import Event
from pretalx.mail.domain.queries import outbox_mails
from pretalx.mail.enums import QueuedMailStates
from pretalx.orga.signals import dashboard_tile
from pretalx.person.domain.queries.profile import submitters_for_event
from pretalx.submission.domain.cfp import access_code_blocker
from pretalx.submission.domain.queries.submission import (
    annotate_submission_count,
    unreviewed_submissions_for_user,
)
from pretalx.submission.models import CfP, Submission, SubmissionStates


def start_redirect_view(request):
    with scopes_disabled():
        orga_events = set(request.user.get_events_with_any_permission())
        speaker_events = set(speaker_events_for_user(request.user))

    # Users with only one event, in only one role, are redirected to that event
    if len(orga_events | speaker_events) == 1 and not (orga_events and speaker_events):
        if orga_events:
            return redirect(orga_events.pop().orga_urls.base)
        return redirect(speaker_events.pop().urls.user_submissions)

    return redirect(reverse("orga:event.list"))


class DashboardEventListView(TemplateView):
    template_name = "orga/event_list.html"

    @property
    def base_queryset(self):
        return self.request.user.get_events_with_any_permission()

    @cached_property
    def queryset(self):
        qs = annotate_submission_count(self.base_queryset).order_by("-date_from")
        if search := self.request.GET.get("q"):
            qs = qs.filter(Q(name__icontains=search) | Q(slug__icontains=search))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_orga_events"] = []
        context["past_orga_events"] = []
        for event in self.queryset:
            if event.date_to >= now().date():
                context["current_orga_events"].insert(0, event)
            else:
                context["past_orga_events"].append(event)
        context["speaker_events"] = speaker_events_for_user(self.request.user)
        return context


class DashboardOrganiserEventListView(PermissionRequired, DashboardEventListView):
    permission_required = "event.view_organiser"

    def get_permission_object(self):
        return self.request.organiser

    @property
    def base_queryset(self):
        return self.request.organiser.events.all()

    @context
    def hide_speaker_events(self):
        return True


class DashboardOrganiserListView(PermissionRequired, TemplateView):
    template_name = "orga/organiser/list.html"
    permission_required = "event.list_organiser"

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
        orgs = organisers_for_user(self.request.user)
        query = self.request.GET.get("q")
        if not query:
            return orgs
        query = query.lower().strip()
        return [org for org in orgs if self.filter_organiser(org, query)]


class EventDashboardView(EventPermissionRequired, TemplateView):
    template_name = "orga/event/dashboard.html"
    permission_required = "event.orga_access_event"

    def get_cfp_tiles(self, _now, can_change_submissions=False):
        result = []
        max_deadline = self.request.event.cfp.max_deadline
        if max_deadline and _now < max_deadline:
            result.append(
                {
                    "large": timeuntil(max_deadline),
                    "small": _("until the CfP ends"),
                    "priority": 40,
                }
            )
            draft_proposals = Submission.all_objects.filter(
                state=SubmissionStates.DRAFT, event=self.request.event
            ).count()
            if draft_proposals and can_change_submissions:
                result.append(
                    {
                        "large": draft_proposals,
                        "small": ngettext_lazy(
                            "unsubmitted proposal draft",
                            "unsubmitted proposal drafts",
                            draft_proposals,
                        ),
                        "priority": 50,
                        "url": self.request.event.orga_urls.send_drafts_reminder,
                        "left": {
                            "text": _("Send reminder"),
                            "url": self.request.event.orga_urls.send_drafts_reminder,
                            "color": "info",
                        },
                    }
                )
        return result

    def get_review_tiles(self):
        result = []
        review_count = self.request.event.reviews.count()
        if review_count:
            active_reviewers = active_reviewers_for_event(self.request.event).count()
            result.append(
                {
                    "large": review_count,
                    "small": ngettext_lazy("review", "reviews", review_count),
                    "url": self.request.event.orga_urls.reviews,
                    "priority": 60,
                    "legend": [
                        {
                            "count": active_reviewers,
                            "label": ngettext_lazy(
                                "active reviewer", "active reviewers", active_reviewers
                            ),
                            "color": "neutral",
                        }
                    ],
                }
            )
        return result

    @cached_property
    def reviews_missing(self):
        is_reviewer = bool(
            user_reviewer_teams_in_event(self.request.user, self.request.event)
        )
        if not is_reviewer:
            return 0
        return unreviewed_submissions_for_user(
            self.request.event, self.request.user
        ).count()

    def get_attention_items(self, can_change_settings, counts):
        event = self.request.event
        items = []
        if can_change_settings and not event.is_public:
            items.append({"type": "live"})
        blocker = (
            access_code_blocker(event)
            if can_change_settings and event.cfp.is_open
            else None
        )
        if blocker == "track":
            items.append(
                {
                    "text": _(
                        "Your CfP is open, but every track requires an access code, so nobody can submit a proposal without one."
                    ),
                    "url": event.cfp.urls.tracks,
                    "action": _("Tracks"),
                    "warning": True,
                }
            )
        elif blocker:
            items.append(
                {
                    "text": _(
                        "Your CfP is open, but nobody can submit a proposal without an access code."
                    ),
                    "url": event.cfp.urls.types,
                    "action": _("Session types"),
                    "warning": True,
                }
            )
        if self.reviews_missing:
            items.append(
                {
                    "count": self.reviews_missing,
                    "text": ngettext_lazy(
                        "proposal is waiting for your review",
                        "proposals are waiting for your review",
                        self.reviews_missing,
                    ),
                    "url": event.orga_urls.reviews,
                    "action": _("Review now"),
                }
            )
        if counts["pending"]:
            states = "&".join(
                f"state=pending_state__{state}"
                for state, __ in SubmissionStates.choices
                if state != SubmissionStates.DRAFT
            )
            items.append(
                {
                    "count": counts["pending"],
                    "text": ngettext_lazy(
                        "submission has pending changes",
                        "submissions have pending changes",
                        counts["pending"],
                    ),
                    "url": event.orga_urls.submissions + f"?{states}",
                    "action": _("See changes"),
                }
            )
        if counts["accepted"]:
            items.append(
                {
                    "count": counts["accepted"],
                    "text": ngettext_lazy(
                        "session is still unconfirmed",
                        "sessions are still unconfirmed",
                        counts["accepted"],
                    ),
                    "url": event.orga_urls.submissions
                    + f"?state={SubmissionStates.ACCEPTED}",
                    "action": _("Show"),
                }
            )
        if self.request.user.has_perm("mail.list_queuedmail", event):
            outbox_count = outbox_mails(event).count()
            if outbox_count:
                items.append(
                    {
                        "count": outbox_count,
                        "text": ngettext_lazy(
                            "email is waiting in the outbox",
                            "emails are waiting in the outbox",
                            outbox_count,
                        ),
                        "url": event.orga_urls.outbox,
                        "action": _("Show"),
                    }
                )
        return items

    def get_plugin_tiles(self):
        tiles = []
        for __, response in dashboard_tile.send_robust(sender=self.request.event):
            if isinstance(response, list):
                tiles.extend(response)
            else:
                tiles.append(response)
        return tiles

    @context
    def activity_groups(self):
        return group_activity_log(
            event_activity_log(self.request.event)[:15], hide_object_models=(Event, CfP)
        )

    def get_context_data(self, **kwargs):
        # Tiles can have priorities
        # Priorities are meant to be between 0 and 100
        # 0 is the first tile, the go-live tile
        # 100+ is whatever can go to the very end
        # actions should be between 10 and 30
        # general stats start at 50
        result = super().get_context_data(**kwargs)
        event = self.request.event
        _now = now()
        today = _now.date()
        can_change_settings = self.request.user.has_perm("event.update_event", event)
        can_change_submissions = self.request.user.has_perm(
            "submission.orga_update_submission", event
        )
        result["tiles"] = self.get_cfp_tiles(
            _now, can_change_submissions=can_change_submissions
        )
        if today < event.date_from:
            days = (event.date_from - today).days
            result["tiles"].append(
                {
                    "large": days,
                    "small": ngettext_lazy(
                        "day until event start", "days until event start", days
                    ),
                    "priority": 10,
                }
            )
        elif today > event.date_to:
            days = (today - event.date_to).days
            result["tiles"].append(
                {
                    "large": days,
                    "small": ngettext_lazy(
                        "day since event end", "days since event end", days
                    ),
                    "priority": 80,
                }
            )
        elif event.date_to != event.date_from:
            result["running_day"] = (today - event.date_from).days + 1
            result["running_day_total"] = (event.date_to - event.date_from).days + 1

        talk_count = event.talks.count()
        accepted_count = event.submissions.filter(
            state=SubmissionStates.ACCEPTED
        ).count()
        confirmed_count = event.submissions.filter(
            state=SubmissionStates.CONFIRMED
        ).count()
        rejected_submission_count = event.submissions.filter(
            state=SubmissionStates.REJECTED
        ).count()
        submission_count = event.submissions.count()
        pending_state_submissions = event.submissions.filter(
            pending_state__isnull=False
        ).count()
        if talk_count or accepted_count:
            result["tiles"].append(
                {
                    # Don’t show 0 here for events that do not use the scheduling
                    # component, instead show accepted + confirmed
                    "large": talk_count or (accepted_count + confirmed_count),
                    "small": ngettext_lazy("session", "sessions", talk_count),
                    "url": event.orga_urls.submissions
                    + f"?state={SubmissionStates.ACCEPTED}&state={SubmissionStates.CONFIRMED}",
                    "priority": 55,
                    "legend": [
                        {
                            "count": confirmed_count,
                            "label": _("confirmed"),
                            "color": "success",
                            "url": event.orga_urls.submissions
                            + f"?state={SubmissionStates.CONFIRMED}",
                        },
                        {
                            "count": accepted_count,
                            "label": _("unconfirmed"),
                            "color": "danger" if accepted_count else "neutral",
                            "url": event.orga_urls.submissions
                            + f"?state={SubmissionStates.ACCEPTED}",
                        },
                    ],
                }
            )
        if submission_count:
            result["tiles"].append(
                {
                    "large": submission_count,
                    "small": ngettext_lazy("proposal", "proposals", submission_count),
                    "url": event.orga_urls.submissions,
                    "priority": 60,
                    "legend": [
                        {
                            "count": accepted_count + confirmed_count,
                            "label": _("accepted"),
                            "color": "success",
                            "url": event.orga_urls.submissions
                            + f"?state={SubmissionStates.ACCEPTED}&state={SubmissionStates.CONFIRMED}",
                        },
                        {
                            "count": rejected_submission_count,
                            "label": _("rejected"),
                            "color": "neutral",
                            "url": event.orga_urls.submissions
                            + f"?state={SubmissionStates.REJECTED}",
                        },
                    ],
                }
            )
        speaker_count = event.speakers.count()
        if speaker_count:
            result["tiles"].append(
                {
                    "large": speaker_count,
                    "small": ngettext_lazy("speaker", "speakers", speaker_count),
                    "url": event.orga_urls.speakers + "?role=speaker",
                    "priority": 56,
                }
            )
        else:
            submitter_count = submitters_for_event(event, include_bare=True).count()
            result["tiles"].append(
                {
                    "large": submitter_count,
                    "small": ngettext_lazy("submitter", "submitters", submitter_count),
                    "url": event.orga_urls.speakers,
                    "priority": 60,
                }
            )
        count = event.queued_mails.filter(state=QueuedMailStates.SENT).count()
        result["tiles"].append(
            {
                "large": count,
                "small": ngettext_lazy("sent email", "sent emails", count),
                "url": event.orga_urls.sent_mails,
                "priority": 80,
            }
        )
        result["tiles"] += self.get_review_tiles()
        result["tiles"] += self.get_plugin_tiles()
        result["tiles"].sort(key=lambda tile: tile.get("priority") or 100)
        result["attention_items"] = self.get_attention_items(
            can_change_settings,
            {"pending": pending_state_submissions, "accepted": accepted_count},
        )
        return result
