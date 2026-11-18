from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.templatetags.static import static
from django.urls import reverse
from django.utils.html import format_html, json_script
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from pretalx.cfp.signals import html_head
from pretalx.common.signals import activitylog_display
from pretalx.orga.signals import nav_event_settings
from pretalx.submission.models import Submission

from .content import apply_to
from .models import FixedSession

PERMISSION = "submission.update_submissiontype"


@receiver(pre_save, sender=Submission, dispatch_uid="fixed_sessions_enforce")
def enforce_fixed_content(sender, instance, raw=False, **kwargs):
    """Every save path (CfP, speaker edit, organiser edit, API) ends here, so
    a core session's content can't be changed anywhere but in this plugin."""
    if not raw:
        apply_to(instance)


@receiver(nav_event_settings, dispatch_uid="fixed_sessions_nav")
def add_settings_nav(sender, request, **kwargs):
    if not request.user.has_perm(PERMISSION, sender):
        return []
    url = reverse("plugins:pretalx_fixed_sessions:list", kwargs={"event": sender.slug})
    return [
        {
            "label": gettext("Fixed sessions"),
            "url": url,
            "active": request.path.startswith(url),
        }
    ]


# CfP pages with the proposal form: the submission wizard and the speaker's
# edit page
FORM_URL_NAMES = {"event.submit", "event.user.submission.edit"}


@receiver(html_head, dispatch_uid="fixed_sessions_html_head")
def add_form_script(sender, request, **kwargs):
    """Fills in and locks the content fields when a core session type is
    chosen. Only a convenience: enforce_fixed_content applies on save anyway."""
    match = getattr(request, "resolver_match", None)
    if not match or "cfp" not in match.namespaces or match.url_name not in FORM_URL_NAMES:
        return ""
    fixed = {
        str(f.submission_type_id): {
            "title": f.title,
            "abstract": f.abstract,
            "description": f.description,
        }
        for f in FixedSession.objects.filter(submission_type__event=sender)
    }
    if not fixed:
        return ""
    # The form drops the session type field when there is only one choice or
    # the type can't be changed; then the script needs the type from here.
    current = ""
    code = match.kwargs.get("code")
    if code:
        submission = sender.submissions.filter(code__iexact=code).first()
        current = submission.submission_type_id if submission else ""
    elif sender.cfp.default_type_id:
        current = sender.cfp.default_type_id
    return json_script(fixed, "fixed-sessions-data") + format_html(
        '<meta name="fixed-sessions" data-current-type="{}" data-notice="{}">'
        '<script defer src="{}"></script>',
        current,
        gettext(
            "This is a core session: its title, abstract and description are "
            "set by the organisers."
        ),
        static("pretalx_fixed_sessions/form.js"),
    )


LOG_ACTIONS = {
    "pretalx_fixed_sessions.applied": _(
        "The fixed content of a core session was applied to its proposals."
    ),
    "pretalx_fixed_sessions.removed": _("A core session's fixed content was removed."),
}


@receiver(activitylog_display, dispatch_uid="fixed_sessions_activitylog_display")
def display_log_entry(sender, activitylog, **kwargs):
    message = LOG_ACTIONS.get(activitylog.action_type)
    if not message:
        return None
    data = activitylog.json_data or {}
    if data.get("session_type"):
        return f"{message} ({data['session_type']})"
    return str(message)
