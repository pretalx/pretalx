from django.dispatch import receiver
from django.templatetags.static import static
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext

from pretalx.cfp.signals import footer_link, html_head
from pretalx.orga.signals import nav_event_settings

from .views import PERMISSION


@receiver(footer_link, dispatch_uid="track_schedule_footer_link")
def add_footer_link(sender, request, **kwargs):
    """pretalx has no plugin hook for the header tabs; the footer is the
    event-wide place a plugin can link from."""
    schedule = sender.current_schedule
    if not schedule or not request.user.has_perm(PERMISSION, schedule):
        return []
    return [
        {
            "label": gettext("Schedule by track"),
            "url": reverse(
                "plugins:pretalx_track_schedule:schedule", kwargs={"event": sender.slug}
            ),
        }
    ]


@receiver(html_head, dispatch_uid="track_schedule_header_tab")
def add_header_tab(sender, request, **kwargs):
    """Adds a "By track" tab next to Schedule, Sessions and Speakers on the
    public schedule pages. pretalx has no plugin hook for these tabs, so a
    small script appends it to the server-rendered tab bar (#header-tabs)."""
    match = getattr(request, "resolver_match", None)
    on_own_page = (
        match is not None
        and "pretalx_track_schedule" in match.namespaces
        and match.url_name == "schedule"
    )
    if not match or not ("agenda" in match.namespaces or on_own_page):
        return ""
    schedule = sender.current_schedule
    if not schedule or not request.user.has_perm(PERMISSION, schedule):
        return ""
    return format_html(
        '<meta name="track-schedule-tab" data-url="{}" data-label="{}">'
        '<script defer src="{}"></script>',
        reverse(
            "plugins:pretalx_track_schedule:schedule", kwargs={"event": sender.slug}
        ),
        gettext("By track"),
        static("pretalx_track_schedule/tab.js"),
    )


@receiver(nav_event_settings, dispatch_uid="track_schedule_settings_nav")
def add_settings_nav(sender, request, **kwargs):
    from .orga_views import SETTINGS_PERMISSION

    if not request.user.has_perm(SETTINGS_PERMISSION, sender):
        return []
    url = reverse(
        "plugins:pretalx_track_schedule:settings", kwargs={"event": sender.slug}
    )
    return [
        {
            "label": gettext("Schedule by track"),
            "url": url,
            "active": request.path.startswith(url),
        }
    ]
