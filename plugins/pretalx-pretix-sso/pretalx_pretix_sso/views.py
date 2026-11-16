import logging
import secrets

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views import View
from django_scopes import scopes_disabled

from pretalx.common.models import ActivityLog
from pretalx.event.models import Event
from pretalx.person.models import User

from . import oidc
from .models import PretixCustomer

logger = logging.getLogger(__name__)
SESSION_KEY = "pretix_sso"


def _event_from_state(state):
    """The event a login attempt belongs to, from the ``<token>.<event slug>``
    state. Only used to send people back to that event when their session no
    longer knows about the attempt, so it does not need to be trusted."""
    _token, _sep, slug = state.partition(".")
    if not slug:
        return None
    with scopes_disabled():
        return Event.objects.filter(slug=slug).first()


def _log_account_event(event, user, action, **data):
    """Record an SSO account change in the event's activity log. pretalx's User
    has no log_action, so the entry is created directly. No email addresses or
    pretix identifiers are stored."""
    ActivityLog.objects.create(
        event=event,
        person=user,
        content_object=user,
        action_type=f"pretalx_pretix_sso.account.{action}",
        data=data or None,
        is_orga_action=False,
    )


def _redirect_uri():
    # Built from the configured site URL, not the request: behind a TLS-terminating
    # proxy the request looks like plain http, and the Host header is client input.
    return settings.SITE_URL.rstrip("/") + reverse("plugins:pretalx_pretix_sso:callback")


class LoginStartView(View):
    def get(self, request, *args, **kwargs):
        event = request.event
        if not oidc.is_enabled(event):
            raise Http404()
        if request.user.is_authenticated:
            return redirect(event.urls.user_submissions)

        # The slug lets the callback find the event even without the session
        state = f"{secrets.token_urlsafe(32)}.{event.slug}"
        nonce = secrets.token_urlsafe(32)
        verifier, challenge = oidc.new_pkce_pair()
        next_url = request.GET.get("next", "")
        if not url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}
        ):
            next_url = ""
        request.session[SESSION_KEY] = {
            "state": state,
            "nonce": nonce,
            "verifier": verifier,
            "event": event.slug,
            "next": next_url,
        }
        try:
            url = oidc.authorization_url(_redirect_uri(), state, nonce, challenge)
        except (requests.RequestException, oidc.OIDCError):
            logger.exception("pretix SSO discovery failed")
            messages.error(request, _("Login with pretix is currently unavailable."))
            return redirect(event.urls.login)
        logger.info("pretix SSO login started for event %s", event.slug)
        return redirect(url)


class CallbackView(View):
    def get(self, request, *args, **kwargs):
        data = request.session.pop(SESSION_KEY, None)
        if not data:
            return self._stale(request)
        with scopes_disabled():
            event = Event.objects.filter(slug=data["event"]).first()
        if not event or not oidc.is_enabled(event):
            raise Http404()

        def fail(message):
            messages.error(request, message)
            return redirect(event.urls.login)

        if request.GET.get("error"):
            # %r: the error code comes from the query string, so keep it on one line
            logger.info(
                "pretix SSO login for event %s ended at pretix: %r",
                event.slug,
                request.GET.get("error")[:100],
            )
            return fail(_("Login with pretix was cancelled."))
        state = request.GET.get("state", "")
        code = request.GET.get("code", "")
        if not code or not secrets.compare_digest(state, data["state"]):
            logger.warning(
                "pretix SSO callback for event %s refused: %s",
                event.slug,
                "missing code" if not code else "state does not match the session",
            )
            return fail(_("Login with pretix failed, please try again."))

        try:
            userinfo = oidc.fetch_userinfo(
                code, _redirect_uri(), data["nonce"], data["verifier"]
            )
        except (oidc.OIDCError, requests.RequestException):
            logger.exception("pretix SSO token exchange failed")
            return fail(_("Login with pretix failed, please try again."))

        email = userinfo.get("email")
        email = email.strip().lower() if isinstance(email, str) else ""
        # Accounts are matched by email, so only trust addresses pretix has verified
        if not email or userinfo.get("email_verified") is not True:
            logger.info(
                "pretix SSO login for event %s refused: no verified email address",
                event.slug,
            )
            return fail(_("Your pretix account has no verified email address."))

        # Prefer the pretix account link: it survives email changes on either side
        link = PretixCustomer.objects.filter(identifier=userinfo["sub"]).first()
        user = link.user if link else User.objects.filter(email__iexact=email).first()
        created = False
        if not user:
            name = userinfo.get("name") or email.split("@")[0]
            try:
                with transaction.atomic():
                    user = User.objects.create_user(
                        password=None,
                        email=email,
                        name=name[:120],
                        locale=getattr(request, "LANGUAGE_CODE", event.locale),
                        timezone=event.timezone,
                    )
                    # Without a password, pretalx sets a random one plus a
                    # reset token for invitations. SSO accounts have neither.
                    user.set_unusable_password()
                    user.pw_reset_token = None
                    user.pw_reset_time = None
                    user.save(
                        update_fields=["password", "pw_reset_token", "pw_reset_time"]
                    )
                created = True
            # pretalx checks email uniqueness before saving (ValidationError);
            # the database constraint catches a race past that (IntegrityError)
            except (IntegrityError, ValidationError):
                # A concurrent callback created the account first
                user = User.objects.filter(email__iexact=email).first()
                if not user:
                    raise

        # SSO is only for speakers: organisers and admins must use their password.
        if user.is_administrator or user.is_superuser or user.teams.exists():
            logger.info(
                "pretix SSO login for event %s refused: user %s is an organiser",
                event.slug,
                user.code,
            )
            return fail(
                _(
                    "This account belongs to an organiser. Please log in with your password."
                )
            )
        if not user.is_active:
            logger.info(
                "pretix SSO login for event %s refused: user %s is deactivated",
                event.slug,
                user.code,
            )
            return fail(_("This account has been deactivated."))

        # pretalx never verified the email of password accounts, so whoever
        # registered this one may not own the address pretix just verified. On the
        # first link by email, drop the password so only the pretix owner can get
        # in (a password reset to the verified address still works).
        previous = PretixCustomer.objects.filter(user=user).first()
        first_link = not link and not previous
        password_disabled = first_link and user.has_usable_password()
        if password_disabled:
            user.set_unusable_password()
            user.save(update_fields=["password"])
            logger.info("Disabled password of user %s on first pretix SSO link", user.code)

        # Remember the pretix account so its orders count as this speaker's tickets.
        # The latest login wins if the user switched pretix accounts.
        PretixCustomer.objects.update_or_create(
            user=user, defaults={"identifier": userinfo["sub"]}
        )
        if created:
            outcome = "created"
        elif first_link:
            outcome = "linked"
        elif previous and previous.identifier != userinfo["sub"]:
            outcome = "moved"
        else:
            outcome = "returning"
        if outcome == "linked":
            _log_account_event(event, user, "linked", password_disabled=password_disabled)
        elif outcome != "returning":
            _log_account_event(event, user, outcome)

        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        logger.info(
            "pretix SSO login succeeded for user %s on event %s (%s account)",
            user.code,
            event.slug,
            outcome,
        )
        if password_disabled:
            messages.info(
                request,
                _(
                    "Your account is now linked to your pretix account, so please log "
                    "in with pretix from now on. Your previous password no longer "
                    "works; use “Forgot password” if you need one."
                ),
            )
        if data["next"] and url_has_allowed_host_and_scheme(
            data["next"], allowed_hosts={request.get_host()}
        ):
            return redirect(data["next"])
        return redirect(event.urls.user_submissions)

    def _stale(self, request):
        """The session has no login in progress: Back or reload after logging in,
        an expired session, or a login finished in another browser."""
        event = _event_from_state(request.GET.get("state", ""))
        if not event or not oidc.is_enabled(event):
            raise Http404()
        if request.user.is_authenticated:
            return redirect(event.urls.user_submissions)
        logger.info(
            "pretix SSO callback for event %s had no login in progress", event.slug
        )
        messages.error(
            request, _("Your login attempt has expired. Please log in with pretix again.")
        )
        return redirect(event.urls.login)
