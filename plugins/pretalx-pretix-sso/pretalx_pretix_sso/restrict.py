"""Make pretix SSO the only way to create an account on SSO-enabled events."""

import logging

from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext as _

from pretalx.cfp.flow import UserStep
from pretalx.cfp.views.auth import LoginView

from .oidc import is_enabled

logger = logging.getLogger(__name__)


def _patch(cls, name, make_wrapper):
    original = getattr(cls, name)
    if getattr(original, "_pretix_sso", False):
        return
    wrapper = make_wrapper(original)
    wrapper._pretix_sso = True
    setattr(cls, name, wrapper)


def _user_step_post(original):
    def post(self, request):
        # The account step only runs for anonymous users, so any POST here is
        # a password login or registration attempt.
        if is_enabled(request.event):
            logger.info(
                "Refused password login/registration in the submission wizard of "
                "event %s: pretix SSO only",
                request.event.slug,
            )
            self.request = request
            messages.error(request, _("Please log in with pretix to continue."))
            return self.get(request)
        return original(self, request)

    return post


def _login_view_post(original):
    def post(self, request, *args, **kwargs):
        # Password login stays available (organisers need it); registration
        # is anything that is not a login attempt.
        is_login = request.POST.get("login_email") and request.POST.get(
            "login_password"
        )
        if is_enabled(request.event) and not is_login:
            logger.info(
                "Refused registration on the login page of event %s: pretix SSO only",
                request.event.slug,
            )
            messages.error(
                request, _("New accounts are created by logging in with pretix.")
            )
            return redirect(request.get_full_path())
        return original(self, request, *args, **kwargs)

    return post


def patch_views():
    _patch(UserStep, "post", _user_step_post)
    _patch(LoginView, "post", _login_view_post)
