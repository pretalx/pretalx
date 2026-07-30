# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import zoneinfo
from contextlib import suppress
from urllib.parse import urljoin, urlparse

from django.apps import apps
from django.conf import settings
from django.core.exceptions import DisallowedHost
from django.db.models import Exists, OuterRef, Subquery
from django.http import Http404
from django.http.request import split_domain_port
from django.shortcuts import get_object_or_404, redirect
from django.urls import Resolver404, resolve
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
from pretalx.event.domain.queries.event import events_for_custom_domain
from pretalx.event.models import Event, Organiser
from pretalx.person.models import SpeakerProfile
from pretalx.schedule.models import Schedule
from pretalx.submission.models import Submission

LOCAL_HOST_NAMES = ("testserver", "localhost", "127.0.0.1")
ANY_DOMAIN_ALLOWED = ("robots.txt", "redirect", "event.css")


class EventMiddleware:
    """Resolves the request's host, organiser and event, and everything that depends on them:

    1. Set request.organiser and request.event
    2. Handle domain-based redirects: custom domains, unknown hosts
    3. Set locale and timezone
    4. Guard against plugin URLs whose plugin is not active for the event
    5. Handle redirects: anonymous users on organiser pages
    6. Activate event scoping
    7. Set CORS headers, and CSP headers for organiser pages on custom domains
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

    def __call__(self, request):
        host = self.get_host(request)
        request.host, request.port = split_domain_port(host)
        request.uses_custom_domain = False
        request.event = None

        try:
            url = resolve(request.path_info)
        except Resolver404:
            # Try to attach the domain to use it for themeing the error page.
            self._attach_event_from_path(request)
            raise

        self._attach_event(request, url)
        if response := self._handle_domain(request, url, host):
            return response

        self._select_locale(request)

        if (
            request.event
            and url.namespaces
            and url.namespaces[0] == "plugins"
            and len(url.namespaces) > 1
        ):
            plugin = url.namespaces[1]
            app = apps.get_app_config(plugin)
            visible = getattr(app.PretalxPluginMeta, "visible", True)
            if visible and plugin not in request.event.plugin_list:
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
                return self._update_csp(request, response)
        if request.event:
            with scope(event=request.event):
                response = self.get_response(request)
        else:
            response = self.get_response(request)

        if is_exempt and "Access-Control-Allow-Origin" not in response:
            response["Access-Control-Allow-Origin"] = "*"
        return self._update_csp(request, response)

    @staticmethod
    def get_host(request):
        # We try three options, in order of decreasing preference.
        if settings.USE_X_FORWARDED_HOST and ("X-Forwarded-Host" in request.headers):
            host = request.headers["X-Forwarded-Host"]
        elif "Host" in request.headers:
            host = request.headers["Host"]
        else:
            # Reconstruct the host using the algorithm from PEP 333.
            host = request.META["SERVER_NAME"]
            server_port = str(request.META["SERVER_PORT"])
            if server_port != ("443" if request.is_secure() else "80"):
                host = f"{host}:{server_port}"
        return host

    @staticmethod
    def _attach_event_from_path(request):
        parts = request.path.strip("/").split("/")
        if not parts or not parts[0]:
            return
        if parts[0] == "orga" and len(parts) >= 3 and parts[1] == "event":
            slug = parts[2]
        else:
            slug = parts[0]
        with suppress(Event.DoesNotExist, ValueError):
            request.event = Event.objects.get(slug__iexact=slug)

    def _attach_event(self, request, url):
        event_slug = url.kwargs.get("event")
        organiser_slug = url.kwargs.get("organiser")
        if organiser_slug and not event_slug:
            request.organiser = get_object_or_404(
                Organiser, slug__iexact=organiser_slug
            )
        if not event_slug:
            return None
        with scopes_disabled():
            queryset = Event.objects.prefetch_related("extra_links").select_related(
                "organiser", "cfp"
            )
            latest_schedule_subquery = (
                Schedule.objects.filter(event=OuterRef("pk"), published__isnull=False)
                .order_by("-published")
                .values("pk")[:1]
            )
            annotations = {"_current_schedule_pk": Subquery(latest_schedule_subquery)}
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
            try:
                request.event = get_object_or_404(queryset, slug__iexact=event_slug)
                request.organiser = request.event.organiser
            except (
                ValueError
            ):  # pragma: no cover -- url regex should prevent malformed slugs
                raise Http404 from None
            return request.event

    def _handle_domain(self, request, url, host):
        if url.url_name in ANY_DOMAIN_ALLOWED or request.path.startswith("/api/"):
            return None

        default_domain, default_port = split_domain_port(settings.SITE_NETLOC)
        on_default_domain = (
            request.host == default_domain and request.port == default_port
        )
        # Debug and local hosts count as default domains
        request.uses_custom_domain = (
            not on_default_domain
            and not settings.DEBUG
            and request.host not in LOCAL_HOST_NAMES
        )

        if request.event:
            return self._handle_event_domain(request)

        if not request.uses_custom_domain:
            # Non-event requests on default domains or debug/local domains are fine
            return None

        if request.path.startswith("/orga"):
            # Non-event orga pages belong on the main domain.
            return redirect(urljoin(settings.SITE_URL, request.get_full_path()))

        if events := events_for_custom_domain(
            request.scheme, host, domain=request.host
        ):
            # Non-event page on custom domain is redirected to most recent event if possible
            request.custom_domain_events = events
            public_event = events.filter(is_public=True).first()
            if public_event:
                return redirect(public_event.urls.base.full())
            # Events exist, but no public ones. We accept leaking the domain (which
            # we do anyways by serving a cert) and show the start page instead of
            # confusing organisers with a 404.
            return None

        # No event given, and we do not know the host requested. This should never happen,
        # as the web server should not have forwarded this request (and provided a cert
        # for it) without knowing it lives here; but caching and races can still happen.
        raise DisallowedHost(f"Unknown host: {host}")

    def _handle_event_domain(self, request):
        if not request.uses_custom_domain:
            if not request.event.custom_domain or request.path.startswith("/orga"):
                return None
            # Event needs custom domain, but request has none
            return redirect(
                urljoin(request.event.urls.base.full(), request.get_full_path())
            )
        # Our request is on *a* custom domain
        if request.event.custom_domain:
            custom_domain = urlparse(request.event.custom_domain)
            event_domain, event_port = split_domain_port(custom_domain.netloc)
            if event_domain == request.host and event_port == request.port:
                # Our request is on the *right* custom domain!
                return None
        # We are on an event page, but under the incorrect domain. Redirecting
        # to the proper domain would leak information, so we will show a 404
        # instead.
        if not request.path.startswith("/orga"):
            raise Http404

    def _handle_orga_url(self, request, url):
        if request.uses_custom_domain:
            return redirect(urljoin(settings.SITE_URL, request.get_full_path()))
        if (
            request.user.is_anonymous
            and url.url_name not in self.UNAUTHENTICATED_ORGA_URLS
        ):
            return get_login_redirect(request)
        return None

    def _update_csp(self, request, response):
        if (
            request.path.startswith("/orga")
            and request.event
            and request.event.custom_domain
        ):
            # We need to update the CSP in order to make our fancy login form work
            response._csp_update = getattr(response, "_csp_update", None) or {}  # noqa: SLF001 -- django-csp convention
            response._csp_update["form-action"] = [request.event.urls.base.full()]  # noqa: SLF001 -- django-csp convention
        return response

    def _select_locale(self, request):
        supported = (
            request.event.locales
            if request.event
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
            if request.event:
                tzname = request.event.timezone
            elif request.user.is_authenticated:
                tzname = request.user.timezone
            else:
                tzname = settings.TIME_ZONE
            timezone.activate(zoneinfo.ZoneInfo(tzname))
            request.timezone = tzname
