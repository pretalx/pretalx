# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import zoneinfo
from contextlib import suppress
from urllib.parse import urljoin

from django.apps import apps
from django.conf import settings
from django.db.models import Exists, OuterRef, Subquery
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import resolve
from django.utils import timezone, translation
from django_scopes import scope, scopes_disabled

from pretalx.common.middleware.locale import (
    get_language_from_browser,
    get_language_from_cookie,
    get_language_from_event,
    get_language_from_query,
    get_language_from_user,
)
from pretalx.common.views.redirect import get_login_redirect
from pretalx.event.models import Event, Organiser
from pretalx.person.models import SpeakerProfile
from pretalx.schedule.models import Schedule
from pretalx.submission.models import Submission


class EventMiddleware:
    """Resolves the request's organiser/event, and everything that depends on them:

    1. Set request.organiser and request.event
    2. Set locale and timezone
    3. Guard against plugin URLs whose plugin is not active for the event
    4. Handle redirects: custom domains, anonymous users
    5. Activate event scoping
    6. Set CORS headers
    """

    UNAUTHENTICATED_ORGA_URLS = (
        "invitation.view",
        "auth",
        "login",
        "auth.reset",
        "auth.recover",
        "event.login",
        "event.auth.reset",
        "event.auth.recover",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def _handle_orga_url(self, request, url):
        if request.uses_custom_domain:
            return redirect(urljoin(settings.SITE_URL, request.get_full_path()))
        if (
            request.user.is_anonymous
            and url.url_name not in self.UNAUTHENTICATED_ORGA_URLS
        ):
            return get_login_redirect(request)
        return None

    def __call__(self, request):
        url = resolve(request.path_info)

        organiser_slug = url.kwargs.get("organiser")
        if organiser_slug:
            request.organiser = get_object_or_404(
                Organiser, slug__iexact=organiser_slug
            )

        event_slug = url.kwargs.get("event")
        if event_slug:
            with scopes_disabled():
                try:
                    queryset = Event.objects.prefetch_related(
                        "extra_links"
                    ).select_related("organiser", "cfp")
                    latest_schedule_subquery = (
                        Schedule.objects.filter(
                            event=OuterRef("pk"), published__isnull=False
                        )
                        .order_by("-published")
                        .values("pk")[:1]
                    )
                    annotations = {
                        "_current_schedule_pk": Subquery(latest_schedule_subquery)
                    }
                    if request.user.is_authenticated:
                        annotations["request_speaker_name"] = Subquery(
                            SpeakerProfile.objects.filter(
                                event=OuterRef("pk"), user=request.user
                            ).values("name")[:1]
                        )
                        if "orga" not in url.namespaces:
                            annotations["has_cfp_submissions"] = Exists(
                                Submission.all_objects.filter(
                                    event=OuterRef("pk"), speakers__user=request.user
                                )
                            )
                    queryset = queryset.annotate(**annotations)
                    request.event = get_object_or_404(queryset, slug__iexact=event_slug)
                except ValueError:  # pragma: no cover -- defensive; URL regex prevents most malformed slugs
                    raise Http404 from None
        event = getattr(request, "event", None)

        self._select_locale(request)

        if (
            event
            and url.namespaces
            and url.namespaces[0] == "plugins"
            and len(url.namespaces) > 1
        ):
            plugin = url.namespaces[1]
            app = apps.get_app_config(plugin)
            visible = getattr(app.PretalxPluginMeta, "visible", True)
            if visible and plugin not in event.plugin_list:
                raise Http404

        is_exempt = (
            url.url_name in ("export", "event.css", "widget.messages")
            if "agenda" in url.namespaces
            else request.path.startswith("/api/")
        )

        if "orga" in url.namespaces or (
            "plugins" in url.namespaces and request.path.startswith("/orga")
        ):
            response = self._handle_orga_url(request, url)
            if response:
                return response
        elif (
            event
            and request.event.custom_domain
            and not request.uses_custom_domain
            and not is_exempt
        ):
            response = redirect(
                urljoin(request.event.custom_domain, request.get_full_path())
            )
            response["Access-Control-Allow-Origin"] = "*"
            return response
        if event:
            with scope(event=event):
                response = self.get_response(request)
        else:
            response = self.get_response(request)

        if is_exempt and "Access-Control-Allow-Origin" not in response:
            response["Access-Control-Allow-Origin"] = "*"
        return response

    def _select_locale(self, request):
        supported = (
            request.event.locales
            if (hasattr(request, "event") and request.event)
            else list(settings.LANGUAGES_INFORMATION)
        )
        language = (
            get_language_from_query(request, supported)
            or get_language_from_user(request, supported)
            or get_language_from_cookie(request, supported)
            or get_language_from_browser(request, supported)
            or get_language_from_event(request, supported)
            or settings.LANGUAGE_CODE
        )
        translation.activate(language)
        request.LANGUAGE_CODE = translation.get_language()

        with suppress(zoneinfo.ZoneInfoNotFoundError):
            if hasattr(request, "event") and request.event:
                tzname = request.event.timezone
            elif request.user.is_authenticated:
                tzname = request.user.timezone
            else:
                tzname = settings.TIME_ZONE
            timezone.activate(zoneinfo.ZoneInfo(tzname))
            request.timezone = tzname
