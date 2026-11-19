"""Patches to pretalx views: make pretix SSO the only way to create an account
on SSO-enabled events, and let the review dashboard report proposals the
ticket check refuses to accept."""

import logging

from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext as _

from pretalx.cfp.flow import UserStep
from pretalx.cfp.views.auth import LoginView
from pretalx.common.exceptions import SubmissionError
from pretalx.orga.views.review import ReviewDashboard

from .oidc import is_enabled

logger = logging.getLogger(__name__)


def _patch(cls, name, make_wrapper):
    original = getattr(cls, name)
    if getattr(original, "_pretix_sso", False):
        return
    wrapper = make_wrapper(original)
    wrapper._pretix_sso = True  # noqa: SLF001 -- marks our own wrapper
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


def _review_dashboard_post(original):
    """The review dashboard's accept/reject form doesn't handle a plugin
    refusing a state change (pretalx turns SubmissionError into a message
    everywhere else): it would fail with a server error, and as the form runs in
    one transaction, every other decision in it would be undone too. Check the
    accepts first and leave out the refused ones, with a message each, so the
    rest are saved."""

    def post(self, request, *args, **kwargs):
        from . import ticket_guard, tickets  # noqa: PLC0415 -- after app loading

        event = request.event
        refused = []
        if (
            "pretalx_pretix_sso" in event.plugin_list
            and tickets.is_configured()
            and not self.get_pending(request)
        ):
            data = request.POST.copy()
            for key, value in request.POST.items():
                if not key.startswith("s-") or value != "accept":
                    continue
                submission = event.submissions.filter(
                    code=key.removeprefix("s-"), state="submitted"
                ).first()
                if submission is None:
                    continue
                message = ticket_guard.refusal(event, submission)
                if message:
                    refused.append(message)
                    del data[key]
            request.POST = data
            # Everything refused: pretalx would add "unable to change all 0
            # proposals"; show only the reasons
            if refused and not any(
                key.startswith("s-") and value in ("accept", "reject")
                for key, value in data.items()
            ):
                for message in refused:
                    messages.error(request, message)
                return redirect(request.path)
        try:
            response = original(self, request, *args, **kwargs)
        except SubmissionError as error:
            # Anything the check above didn't foresee: report it instead of a
            # server error (nothing in this form was saved)
            messages.error(request, str(error))
            return redirect(request.path)
        for message in refused:
            messages.error(request, message)
        return response

    return post


def patch_views():
    _patch(UserStep, "post", _user_step_post)
    _patch(LoginView, "post", _login_view_post)
    _patch(ReviewDashboard, "post", _review_dashboard_post)
