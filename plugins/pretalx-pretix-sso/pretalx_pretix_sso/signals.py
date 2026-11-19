import logging

from django.dispatch import receiver
from django.templatetags.static import static
from django.urls import resolve, reverse
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from pretalx.cfp.signals import html_head
from pretalx.common.exceptions import SubmissionError
from pretalx.common.signals import activitylog_display
from pretalx.orga.signals import dashboard_tile, html_above_orga_page, nav_event
from pretalx.submission.signals import before_submission_state_change

from . import ticket_guard, tickets
from .oidc import is_configured
from .orga_views import VIEW_PERMISSION

logger = logging.getLogger(__name__)

LOGIN_URL_NAMES = {"event.login"}


@receiver(html_head, dispatch_uid="pretix_sso_html_head")
def add_login_button(sender, request, **kwargs):
    match = getattr(request, "resolver_match", None)
    if not match or "cfp" not in match.namespaces:
        return ""
    # The wizard rewrites resolver_match.kwargs["step"] to the next step while
    # rendering, so read the current step from the URL itself.
    in_wizard = (
        match.url_name == "event.submit"
        and resolve(request.path_info).kwargs.get("step") == "user"
    )
    if not (match.url_name in LOGIN_URL_NAMES or in_wizard) or not is_configured():
        return ""
    if request.user.is_authenticated:
        return ""
    login_url = reverse(
        "plugins:pretalx_pretix_sso:login", kwargs={"event": sender.slug}
    )
    # In the submission wizard, come back to the same step after logging in
    next_url = request.path if in_wizard else request.GET.get("next")
    if next_url:
        login_url += "?" + urlencode({"next": next_url})
    return format_html(
        '<meta name="pretix-sso-login" content="{}" data-label="{}" data-or="{}"'
        ' data-exclusive="{}">'
        '<script defer src="{}"></script>',
        login_url,
        gettext("Log in with pretix"),
        gettext("or"),
        # In the wizard, pretix SSO replaces password login and registration;
        # on the login page it replaces registration only.
        "all" if in_wizard else "register",
        static("pretalx_pretix_sso/login.js"),
    )


@receiver(nav_event, dispatch_uid="pretix_sso_nav_event")
def add_tickets_nav(sender, request, **kwargs):
    if not request.user.has_perm(VIEW_PERMISSION, sender):
        return []
    url = reverse("plugins:pretalx_pretix_sso:tickets", kwargs={"event": sender.slug})
    return [
        {
            "label": gettext("pretix tickets"),
            "url": url,
            "active": request.path.startswith(url),
            "icon": "ticket",
        }
    ]


LOG_ACTIONS = {
    "pretalx_pretix_sso.override.set": _(
        "A speaker was marked as covered for pretix tickets."
    ),
    "pretalx_pretix_sso.override.removed": _(
        "A speaker's pretix ticket override was removed."
    ),
    "pretalx_pretix_sso.account.created": _(
        "A speaker account was created by logging in with pretix."
    ),
    "pretalx_pretix_sso.account.moved": _(
        "A speaker account was linked to a different pretix account."
    ),
}


@receiver(activitylog_display, dispatch_uid="pretix_sso_activitylog_display")
def display_log_entry(sender, activitylog, **kwargs):
    action = activitylog.action_type
    if action == "pretalx_pretix_sso.tag.synced":
        data = activitylog.json_data or {}
        text = gettext(
            'The "{tag}" tag was synced with pretix tickets: added to {added}, '
            "removed from {removed} proposals."
        ).format(
            tag=data.get("tag", "needsTicket"),
            added=data.get("added", 0),
            removed=data.get("removed", 0),
        )
        # Entries from before the hasTicket tag only cover needsTicket
        if has_ticket := data.get("has_ticket"):
            text += " " + gettext(
                'The "{tag}" tag: added to {added}, removed from {removed} proposals.'
            ).format(
                tag=has_ticket.get("tag", "hasTicket"),
                added=has_ticket.get("added", 0),
                removed=has_ticket.get("removed", 0),
            )
        return text
    if action == "pretalx_pretix_sso.tag.sync_failed":
        data = activitylog.json_data or {}
        if data.get("reason") == "pretix":
            return gettext(
                'The "{tag}" tag sync failed: pretix could not be reached or returned '
                "unexpected data. No tags were changed."
            ).format(tag=data.get("tag", "needsTicket"))
        return gettext(
            'The "{tag}" tag sync failed because of an unexpected error. Details are '
            "in the server log."
        ).format(tag=data.get("tag", "needsTicket"))
    if action == "pretalx_pretix_sso.account.linked":
        if (activitylog.json_data or {}).get("password_disabled"):
            return gettext(
                "An existing speaker account was linked to a pretix account, and its "
                "password was disabled."
            )
        return gettext("An existing speaker account was linked to a pretix account.")
    return LOG_ACTIONS.get(action)


# Accepting a proposal needs a covered speaker (ticket_guard). Blocking the
# step into "accepted" (or straight into "confirmed") keeps ticketless
# proposals out of the schedule: a released schedule shows confirmed ones only.
ACCEPTED_STATES = ("accepted", "confirmed")


@receiver(before_submission_state_change, dispatch_uid="pretix_sso_require_ticket")
def require_ticket_to_accept(sender, submission, new_state, user=None, **kwargs):
    if new_state not in ACCEPTED_STATES or not tickets.is_configured():
        return
    # Organisers creating an already-accepted proposal: pretalx asks before the
    # speakers are added, so there is nothing to check yet; the banner and the
    # dashboard tile show it afterwards
    if submission._state.adding:
        return
    if submission.state in ACCEPTED_STATES:
        return
    message = ticket_guard.refusal(sender, submission)
    if message:
        raise SubmissionError(message)


INACTIVE_STATES = ("rejected", "withdrawn", "canceled", "deleted", "draft")


@receiver(html_above_orga_page, dispatch_uid="pretix_sso_ticket_banner")
def ticket_banner(sender, request, **kwargs):
    """A warning on a proposal's organiser pages when no speaker is covered.
    Uses the cached ticket data; fetches from pretix only when nothing is
    cached (at most once an hour per web process)."""
    match = getattr(request, "resolver_match", None)
    code = match.kwargs.get("code") if match else None
    if (
        not code
        or not (match.url_name or "").startswith("submissions.")
        or not tickets.is_configured()
        or not request.user.has_perm(VIEW_PERMISSION, sender)
    ):
        return ""
    submission = sender.submissions.filter(code__iexact=code).first()
    if submission is None or submission.state in INACTIVE_STATES:
        return ""
    tickets_url = reverse(
        "plugins:pretalx_pretix_sso:tickets", kwargs={"event": sender.slug}
    )
    try:
        covered = ticket_guard.is_covered(sender, submission, fetch_missing=True)
    except tickets.LOOKUP_ERRORS:
        return format_html(
            '<div class="alert alert-warning"><div>{} <a href="{}">{}</a></div></div>',
            gettext(
                "The pretix tickets of this proposal's speakers could not be checked."
            ),
            tickets_url,
            gettext("pretix tickets"),
        )
    if covered:
        return ""
    return format_html(
        '<div class="alert alert-danger"><div>{} <a href="{}">{}</a></div></div>',
        gettext("No speaker of this proposal has a paid pretix ticket."),
        tickets_url,
        gettext("pretix tickets"),
    )


@receiver(dashboard_tile, dispatch_uid="pretix_sso_ticket_tile")
def ticket_tile(sender, **kwargs):
    """Accepted and confirmed sessions without a covered speaker. pretalx adds
    whatever a receiver returns, errors included, so this never raises."""
    try:
        if not tickets.is_configured():
            return []
        sessions = list(
            sender.submissions.filter(state__in=ACCEPTED_STATES).prefetch_related(
                "speakers__user__pretix_customer"
            )
        )
        url = reverse(
            "plugins:pretalx_pretix_sso:tickets", kwargs={"event": sender.slug}
        )
        missing = ticket_guard.uncovered(sender, sessions)
    except tickets.LOOKUP_ERRORS:
        return [
            {
                "large": "?",
                "small": gettext("pretix tickets could not be checked"),
                "url": url,
                "priority": 40,
            }
        ]
    except Exception:
        logger.warning("pretix ticket dashboard tile failed", exc_info=True)
        return []
    if not missing:
        return []
    return [
        {
            "large": len(missing),
            "small": gettext("accepted sessions without a pretix ticket"),
            "url": url,
            "priority": 15,
        }
    ]
