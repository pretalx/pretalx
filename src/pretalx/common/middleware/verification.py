# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import resolve, reverse

from pretalx.common.views.helpers import is_htmx
from pretalx.person.enums import EmailVerificationState


class EmailVerificationMiddleware:
    """Sends unverified users to the verification page."""

    EXEMPT_NAMESPACES = frozenset(("api",))
    EXEMPT_URL_NAMES = frozenset(
        (
            # Verification pages
            "cfp:event.verification",
            "cfp:event.verify",
            "orga:auth.verification",
            "orga:auth.verify",
            "orga:event.auth.verify",
            # Logging out or recovering
            "cfp:event.logout",
            "cfp:event.auth",
            "cfp:event.reset",
            "cfp:event.recover",
            "orga:logout",
            "orga:auth.reset",
            "orga:auth.recover",
            "orga:event.auth.reset",
            "orga:event.auth.recover",
            # Claiming invites
            "cfp:event.claim",
            "cfp:invitation.view",
            "orga:invitation.view",
            # Never lose submissions
            "cfp:event.submit",
            "cfp:event.cfp.restart",
            # Static and heper views
            "agenda:event.css",
            "cfp:locale.set",
            "cfp:locale.set_global",
            "redirect",
            "shortlink",
        )
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self._gate(request) or self.get_response(request)

    def _gate(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None
        if user.email_verification_state != EmailVerificationState.UNVERIFIED:
            return None
        if self.is_exempt(resolve(request.path_info)):
            return None
        return self._redirect(request)

    @classmethod
    def is_exempt(cls, url):
        if url.namespaces and url.namespaces[0] in cls.EXEMPT_NAMESPACES:
            return True
        return ":".join([*url.namespaces, url.url_name or ""]) in cls.EXEMPT_URL_NAMES

    @staticmethod
    def _redirect(request):
        event = getattr(request, "event", None)
        if event and not request.path.startswith("/orga"):
            target = reverse("cfp:event.verification", kwargs={"event": event.slug})
        else:
            target = reverse("orga:auth.verification")
        if is_htmx(request):
            # Prevent htmx from showing the verification page
            response = HttpResponse(status=286)
            response["HX-Redirect"] = target
            return response
        return redirect(target)
