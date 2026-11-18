from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext

from pretalx.cfp.signals import footer_link
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
