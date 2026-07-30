# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import time

from django.conf import settings
from django.contrib.sessions.backends.base import UpdateError
from django.contrib.sessions.middleware import (
    SessionMiddleware as BaseSessionMiddleware,
)
from django.http.request import split_domain_port
from django.middleware.csrf import CSRF_SESSION_KEY
from django.middleware.csrf import CsrfViewMiddleware as BaseCsrfMiddleware
from django.utils.cache import patch_vary_headers
from django.utils.http import http_date


class SessionMiddleware(BaseSessionMiddleware):
    """We override the default implementation from Django.

    We do this because we need to handle cookie domains differently
    depending on whether we are on the main domain or a custom domain.
    """

    def __init__(self, get_response, *args, **kwargs):
        super().__init__(*args, get_response=get_response, **kwargs)
        self.get_response = get_response

    def process_response(self, request, response):
        try:
            accessed = request.session.accessed
            modified = request.session.modified
            empty = request.session.is_empty()
        except AttributeError:
            pass
        else:
            # First check if we need to delete this cookie.
            # The session should be deleted only if the session is entirely empty
            if settings.SESSION_COOKIE_NAME in request.COOKIES and empty:
                response.delete_cookie(settings.SESSION_COOKIE_NAME)
                return response
            if accessed:
                patch_vary_headers(response, ("Cookie",))
            if modified or settings.SESSION_SAVE_EVERY_REQUEST:
                max_age = None
                expires = None
                if not request.session.get_expire_at_browser_close():
                    max_age = request.session.get_expiry_age()
                    expires_time = time.time() + max_age
                    expires = http_date(expires_time)
                # Save the session data and refresh the client cookie.
                # Skip session save for 500 responses, refs #3881.
                if response.status_code != 500:
                    try:
                        request.session.save()
                    except UpdateError:
                        request.session.create()
                    response.set_cookie(
                        settings.SESSION_COOKIE_NAME,
                        request.session.session_key,
                        max_age=max_age,
                        expires=expires,
                        domain=get_cookie_domain(request),
                        path=settings.SESSION_COOKIE_PATH,
                        secure=request.scheme == "https",
                        httponly=settings.SESSION_COOKIE_HTTPONLY or None,
                        samesite=settings.SESSION_COOKIE_SAMESITE,
                    )
        return response

    def __call__(self, request):
        self.process_request(request)
        response = self.get_response(request)
        return self.process_response(request, response)


class CsrfViewMiddleware(BaseCsrfMiddleware):
    """We override the default implementation from Django.

    We do this because we need to handle cookie domains differently
    depending on whether we are on the main domain or a custom domain.
    """

    def _set_csrf_cookie(self, request, response):
        # If CSRF_COOKIE is unset, then CsrfViewMiddleware.process_view was
        # never called, probably because a request middleware returned a response
        # (for example, contrib.auth redirecting to a login page).
        if settings.CSRF_USE_SESSIONS:
            if request.session.get(CSRF_SESSION_KEY) != request.META["CSRF_COOKIE"]:
                request.session[CSRF_SESSION_KEY] = request.META["CSRF_COOKIE"]
        else:
            # Set the CSRF cookie even if it's already set, so we renew
            # the expiry timer.
            response.set_cookie(
                settings.CSRF_COOKIE_NAME,
                request.META["CSRF_COOKIE"],
                max_age=settings.CSRF_COOKIE_AGE,
                domain=get_cookie_domain(request),
                path=settings.CSRF_COOKIE_PATH,
                secure=request.scheme == "https",
                httponly=settings.CSRF_COOKIE_HTTPONLY,
                samesite=settings.CSRF_COOKIE_SAMESITE,
            )
            # Content varies with the CSRF cookie, so set the Vary header.
            patch_vary_headers(response, ("Cookie",))


def get_cookie_domain(request):
    if "." not in request.host:
        # As per spec, browsers do not accept cookie domains without dots in it,
        # e.g. "localhost", see http://curl.haxx.se/rfc/cookie_spec.html
        return None

    default_domain, _ = split_domain_port(settings.SITE_NETLOC)
    # If we are on our main domain, set the cookie domain the user has chosen. Else
    # we are on an organiser's custom domain, set no cookie domain, as we do not want
    # the cookies to be present on any other domain. Setting an explicit value can be
    # dangerous, see http://erik.io/blog/2014/03/04/definitive-guide-to-cookie-domains/
    return settings.SESSION_COOKIE_DOMAIN if request.host == default_domain else None
