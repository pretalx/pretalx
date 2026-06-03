# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import textwrap
from contextlib import suppress
from urllib.parse import unquote

from csp.decorators import csp_update
from django.conf import settings
from django.contrib import messages
from django.http import (
    Http404,
    HttpResponse,
    HttpResponsePermanentRedirect,
    HttpResponseRedirect,
    JsonResponse,
)
from django.urls import resolve, reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.translation import gettext, pgettext_lazy
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import cache_page
from django.views.generic import TemplateView, View
from django_context_decorator import context

from pretalx.agenda.views.ascii import draw_ascii_schedule
from pretalx.common.exporter import (
    get_schedule_exporter_content,
    get_schedule_exporters,
)
from pretalx.common.text.phrases import phrases
from pretalx.common.text.xml import strip_control_characters
from pretalx.common.views.mixins import (
    EventPermissionRequired,
    PermissionRequired,
    SocialMediaCardMixin,
)
from pretalx.schedule.domain.changelog import build_changelog
from pretalx.schedule.interfaces.exporters import ScheduleData
from pretalx.submission.domain.queries.submission import signed_up_submission_codes


class EventSocialMediaCard(SocialMediaCardMixin, EventPermissionRequired, View):
    permission_required = "event.view_event"


class ScheduleMixin:
    @cached_property
    def version(self):
        if version := self.kwargs.get("version"):
            return unquote(version)
        return None

    def get_object(self):
        schedule = None
        if self.version:
            with suppress(Exception):
                schedule = (
                    self.request.event.schedules.filter(version__iexact=self.version)
                    .select_related("event")
                    .first()
                )
        schedule = schedule or self.request.event.current_schedule
        if schedule:
            # make use of existing caches and prefetches
            schedule.event = self.request.event
        return schedule

    @context
    @cached_property
    def schedule(self):
        return self.get_object()

    def dispatch(self, request, *args, **kwargs):
        if version := request.GET.get("version"):
            kwargs["version"] = version
            return HttpResponsePermanentRedirect(
                reverse(
                    f"agenda:versioned-{request.resolver_match.url_name}",
                    args=args,
                    kwargs=kwargs,
                )
            )
        return super().dispatch(request, *args, **kwargs)


class ExporterView(EventPermissionRequired, ScheduleMixin, TemplateView):
    permission_required = "schedule.list_schedule"

    def get(self, request, *args, **kwargs):
        url = resolve(self.request.path_info)
        if url.url_name == "export":
            name = url.kwargs.get("name") or unquote(self.request.GET.get("exporter"))
        else:
            name = url.url_name

        name = name.removeprefix("export.")
        response = get_schedule_exporter_content(request, name, self.schedule)
        if not response:
            raise Http404
        return response


@method_decorator(csp_update(settings.VITE_CSP_UPDATE), name="dispatch")
class ScheduleView(PermissionRequired, ScheduleMixin, TemplateView):
    template_name = "agenda/schedule.html"
    permission_required = "schedule.view_schedule"

    def get_text(self, request, **kwargs):
        data = ScheduleData(
            event=self.request.event,
            schedule=self.schedule,
            with_accepted=False,
            with_breaks=True,
        ).data
        event_name = strip_control_characters(request.event.name)
        response_start = textwrap.dedent(f"""
        \033[1m{event_name}\033[0m

        Get different formats:
           curl {request.event.urls.schedule.full()}\\?format=table (default)
           curl {request.event.urls.schedule.full()}\\?format=list

        """)
        output_format = request.GET.get("format", "table")
        if output_format not in ("list", "table"):
            output_format = "table"
        try:
            result = draw_ascii_schedule(data, output_format=output_format)
        except StopIteration:  # pragma: no cover -- grid drawing fails on degenerate data; fallback is defensive
            result = draw_ascii_schedule(data, output_format="list")
        result += "\n\n  📆 powered by pretalx"
        return HttpResponse(
            response_start + result, content_type="text/plain; charset=utf-8"
        )

    def dispatch(self, request, **kwargs):
        if not self.has_permission() and self.request.user.has_perm(
            "submission.list_featured_submission", self.request.event
        ):
            messages.success(request, _("Our schedule is not live yet."))
            return HttpResponseRedirect(self.request.event.urls.featured)
        return super().dispatch(request, **kwargs)

    def get(self, request, **kwargs):
        accept_header = request.headers.get("Accept") or ""

        if getattr(self, "is_html_export", False):  # pragma: no cover
            # set only by the export_schedule_html management command
            return super().get(request, **kwargs)

        # No Accept header or just "*/*" (curl's default) - return text
        if not accept_header or accept_header.strip() == "*/*":
            return self.get_text(request, **kwargs)

        # Anything else listing "*/*" or HTML explicitly
        if request.accepts("text/html"):
            return super().get(request, **kwargs)

        if request.accepts("text/plain"):
            return self.get_text(request, **kwargs)

        export_headers = {
            "frab_xml": ["application/xml", "text/xml"],
            "frab_json": ["application/json"],
        }
        for url_name, headers in export_headers.items():
            if any(request.accepts(header) for header in headers):
                target_url = getattr(self.request.event.urls, url_name).full()
                response = HttpResponseRedirect(target_url)
                response.status_code = 303
                return response

        return super().get(request, **kwargs)

    def get_object(self):
        if self.version == "wip":
            return self.request.event.wip_schedule
        schedule = super().get_object()
        if not schedule:
            raise Http404
        return schedule

    def get_permission_object(self):
        return self.object

    @context
    def exporters(self):
        return [
            exporter
            for exporter in get_schedule_exporters(self.request, public=True)
            if exporter.show_public
        ]

    @context
    def show_talk_list(self):
        return (
            self.request.path.endswith("/talk/")
            or self.request.event.display_settings["schedule"] == "list"
        )


@cache_page(60 * 60 * 24)
def schedule_messages(request, **kwargs):
    """This view is cached for a day, as it is small and non-critical, but loaded synchronously."""
    strings = {
        "answer_no": _("No"),
        "answer_yes": _("Yes"),
        "clear_filters": _("Clear filters"),
        "close_filters": _("Close filters"),
        "dismiss": _("Dismiss"),
        "favs_not_logged_in": _(
            "You're currently not logged in, so your favourited sessions will only be stored locally in your browser."
        ),
        "favs_not_saved": _(
            "Your favourites could only be saved locally in your browser."
        ),
        "filter": phrases.base.filter_action,
        "filters": _("Filters"),
        "jump_to_now": _("Jump to now"),
        "languages": _("Languages"),
        "no_file_provided": _("No file provided"),
        "no_location": _("No location"),
        "no_matching_sessions": _("No sessions match your current filters."),
        "no_response": _("No response"),
        "not_recorded": _("Not recorded"),
        # Reuses the existing catalogue entry from common/powered_by.html so
        # the widget footer doesn't introduce a duplicate msgid.
        "powered_by": gettext("powered by <a %(a_attr)s>pretalx</a>")
        % {"a_attr": 'href="https://pretalx.com" target="_blank" rel="noopener"'},
        "recording": pgettext_lazy("schedule filter", "Recording"),
        "resource": _("Resource"),
        "schedule_load_error": _(
            "An error occurred while loading the schedule. Please try again later."
        ),
        "schedule_empty": _(
            "The schedule is not yet available. Please check back later!"
        ),
        "show_results": _("Show results"),
        "search": phrases.base.search,
        "see_also": _("See also:"),
        "signup": _("Sign up"),
        "signup_section": _("Signup"),
        "signup_required": _("Requires signup"),
        "signup_full": _("This session is currently full."),
        "signup_signed_up": _("You are signed up for this session."),
        "signup_only": _("Only sessions requiring signup"),
        "signup_hide_full": _("Hide full sessions"),
        "signups_not_loaded": _(
            "Your signed-up sessions could not be loaded. Please try again later."
        ),
        "tags": _("Tags"),
        "toggle_favs": _("Toggle favourites filter"),
        "toggle_signups": _("Toggle signed-up filter"),
        "tracks": _("Tracks"),
    }
    strings = {key: str(value) for key, value in strings.items()}
    return JsonResponse(strings)


def talk_sort_key(talk):
    room = talk.room
    return (talk.start, room.position if room.position is not None else room.id)


class ScheduleNoJsView(ScheduleView):
    template_name = "agenda/schedule_nojs.html"

    def get_schedule_data(self):
        schedule = self.get_object()
        data = ScheduleData(
            event=self.request.event,
            schedule=schedule,
            with_accepted=schedule and not schedule.version,
            with_breaks=True,
        ).data
        for date in data:
            rooms = date.pop("rooms")
            talks = [talk for room in rooms for talk in room.get("talks", [])]
            talks.sort(key=talk_sort_key)
            date["talks"] = talks
        return {"data": list(data)}

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result.update(**self.get_schedule_data())
        result["day_count"] = len(result.get("data", []))
        result["signed_up_codes"] = signed_up_submission_codes(
            self.request.event, self.request.user
        )
        return result


class ChangelogView(EventPermissionRequired, TemplateView):
    template_name = "agenda/changelog.html"
    permission_required = "schedule.list_schedule"

    @context
    def schedules(self):
        return build_changelog(self.request.event)
