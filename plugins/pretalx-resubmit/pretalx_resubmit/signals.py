from django.dispatch import receiver
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext

from pretalx.cfp.signals import html_above_submission_list, html_head
from pretalx.common.signals import activitylog_display

from .resubmit import can_resubmit_to, eligible_sources


@receiver(html_above_submission_list, dispatch_uid="resubmit_submission_list")
def show_resubmit_panel(sender, request, **kwargs):
    if not can_resubmit_to(sender):
        return ""
    sources = eligible_sources(sender, request.user)
    if not sources:
        return ""
    return render_to_string(
        "pretalx_resubmit/_panel.html",
        {"event": sender, "sources": sources},
        request=request,
    )


# The event's start and CfP pages, whose button row gets a "Resubmit" button
BUTTON_URL_NAMES = {"event.landing", "event.start"}


@receiver(html_head, dispatch_uid="resubmit_html_head")
def add_resubmit_button(sender, request, **kwargs):
    match = getattr(request, "resolver_match", None)
    if (
        not match
        or "cfp" not in match.namespaces
        or match.url_name not in BUTTON_URL_NAMES
    ):
        return ""
    if not request.user.is_authenticated or not can_resubmit_to(sender):
        return ""
    if not eligible_sources(sender, request.user):
        return ""
    return format_html(
        '<meta name="pretalx-resubmit" content="{}" data-label="{}">'
        '<script defer src="{}"></script>',
        reverse("plugins:pretalx_resubmit:list", kwargs={"event": sender.slug}),
        gettext("Resubmit a previous proposal"),
        static("pretalx_resubmit/button.js"),
    )


@receiver(activitylog_display, dispatch_uid="resubmit_activitylog_display")
def display_log_entry(sender, activitylog, **kwargs):
    if activitylog.action_type != "pretalx_resubmit.resubmitted":
        return None
    data = activitylog.json_data or {}
    return gettext(
        "The proposal was resubmitted from “{title}” ({code}) in the event {event}."
    ).format(
        title=data.get("source_title", ""),
        code=data.get("source_code", ""),
        event=data.get("source_event", ""),
    )
