from django.dispatch import receiver
from django.templatetags.static import static
from django.urls import resolve, reverse
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from pretalx.cfp.signals import html_head
from pretalx.common.signals import activitylog_display
from pretalx.orga.signals import nav_event

from .oidc import is_configured
from .orga_views import VIEW_PERMISSION

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
    "pretalx_pretix_sso.override.set": _("A speaker was marked as covered for pretix tickets."),
    "pretalx_pretix_sso.override.removed": _("A speaker's pretix ticket override was removed."),
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
