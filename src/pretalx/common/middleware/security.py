# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from urllib.parse import quote

from django.contrib.auth import logout
from django.core.exceptions import BadRequest
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import resolve, reverse
from django.utils.deprecation import MiddlewareMixin

from pretalx.common.middleware.utils import UNAUTHENTICATED_ORGA_URLS
from pretalx.common.security import (
    SessionInvalidError,
    SessionReauthRequiredError,
    assert_session_valid,
)
from pretalx.common.views.helpers import get_htmx_current_url, htmx_redirect, is_htmx
from pretalx.common.views.redirect import get_login_redirect


class RejectInvalidInputMiddleware(MiddlewareMixin):
    """
    Block requests containing null bytes in GET or POST params or URL paths.

    These requests fail later on database access, which clutters our error logs
    when a vulnerability spammer, sorry, scanner runs blindly against pretalx.
    """

    def process_request(self, request):
        if (
            "\x00" in request.path
            or "\x00" in request.META["QUERY_STRING"]
            or "%00" in request.META["QUERY_STRING"]
        ):
            raise BadRequest("Invalid characters in input.")

        # Multipart form data can contain legitimate null bytes, so we stick
        # to x-ww-form-urlencoded. PUT and PATCH do not populate request.POST,
        # so we would have to parse request.body. Scanners stick to GET and
        # POST most of the time, so that's not worth it for now.
        if (
            request.method == "POST"
            and request.content_type == "application/x-www-form-urlencoded"
            and any(
                "\x00" in item
                for key, value_list in request.POST.lists()
                for item in (key, *value_list)
            )
        ):
            raise BadRequest("Invalid characters in input.")


class SessionValidityMiddleware:
    """Sessions that have been idle for longer than the relative session
    timeout have to enter a password, and sessions older than the absolute
    session timeout are logged out. Only applies to the organiser area.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self._gate(request) or self.get_response(request)

    def _gate(self, request):
        if not getattr(request, "is_orga_url", False):
            return None
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None
        url_name = resolve(request.path_info).url_name
        if url_name in UNAUTHENTICATED_ORGA_URLS:
            return None

        try:
            assert_session_valid(request)
        except SessionInvalidError:
            logout(request)
            if self.is_background_request(request):
                return self._unauthorized(self.login_url(request))
            return get_login_redirect(request)
        except SessionReauthRequiredError:
            if url_name != "user.reauth":
                return self._redirect(request, reverse("orga:user.reauth"))
        return None

    @staticmethod
    def is_background_request(request):
        # Set by orgaFetch and api.js to indicate a login page would be useless
        return request.headers.get("X-Requested-With") == "XMLHttpRequest"

    @staticmethod
    def login_url(request):
        event = getattr(request, "event", None)
        return str(event.orga_urls.login) if event else reverse("orga:login")

    @staticmethod
    def _unauthorized(target):
        # For background requests
        return JsonResponse(
            {"detail": "Authentication required"},
            status=401,
            headers={"X-Login-Url": target},
        )

    @classmethod
    def _redirect(cls, request, target):
        if cls.is_background_request(request):
            return cls._unauthorized(target)
        if is_htmx(request):
            next_url = get_htmx_current_url(request) or request.get_full_path()
            return htmx_redirect(f"{target}?next={quote(next_url)}")
        return redirect(f"{target}?next={quote(request.get_full_path())}")
