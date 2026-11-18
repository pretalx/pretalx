from django.db.models.signals import m2m_changed, post_save, pre_save
from django.dispatch import receiver
from django.templatetags.static import static
from django.urls import reverse
from django.utils.html import format_html, json_script
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from pretalx.cfp.signals import html_head
from pretalx.common.signals import activitylog_display
from pretalx.orga.signals import nav_event_settings
from pretalx.submission.models import Answer, QuestionVariant, Submission

from .content import apply_answers, apply_to, is_writing
from .models import FixedSession

PERMISSION = "submission.update_submissiontype"


@receiver(pre_save, sender=Submission, dispatch_uid="fixed_sessions_enforce")
def enforce_fixed_content(sender, instance, raw=False, **kwargs):
    """Every save path (CfP, speaker edit, organiser edit, API) ends here, so
    a core session's content can't be changed anywhere but in this plugin."""
    if not raw:
        apply_to(instance)


@receiver(post_save, sender=Submission, dispatch_uid="fixed_sessions_answers_on_save")
def add_fixed_answers(sender, instance, raw=False, **kwargs):
    """Creates the fixed answers a proposal doesn't have yet, e.g. after its
    session type changed to a core session."""
    if not raw:
        apply_answers(instance)


@receiver(post_save, sender=Answer, dispatch_uid="fixed_sessions_answer_saved")
def enforce_fixed_answer(sender, instance, raw=False, **kwargs):
    if raw or is_writing() or not instance.submission_id:
        return
    apply_answers(instance.submission, question_id=instance.question_id)


@receiver(
    m2m_changed, sender=Answer.options.through, dispatch_uid="fixed_sessions_options"
)
def enforce_fixed_options(sender, instance, action, reverse, **kwargs):
    """pretalx sets a choice answer's options after saving the answer."""
    if reverse or is_writing() or not action.startswith("post_"):
        return
    if instance.submission_id:
        apply_answers(instance.submission, question_id=instance.question_id)


def _answer_value(fixed_answer):
    """The fixed answer as the CfP form field takes it."""
    variant = fixed_answer.question.variant
    if variant == QuestionVariant.CHOICES:
        option = fixed_answer.options.first()
        return str(option.pk) if option else ""
    if variant == QuestionVariant.MULTIPLE:
        return [str(option.pk) for option in fixed_answer.options.all()]
    if variant == QuestionVariant.BOOLEAN:
        return fixed_answer.answer == "True"
    return fixed_answer.answer


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
    if (
        not match
        or "cfp" not in match.namespaces
        or match.url_name not in FORM_URL_NAMES
    ):
        return ""
    fixed = {
        str(f.submission_type_id): {
            "title": f.title,
            "abstract": f.abstract,
            "description": f.description,
            "track": str(f.track_id or ""),
            "answers": {
                f"question_{a.question_id}": _answer_value(a) for a in f.answers.all()
            },
        }
        for f in FixedSession.objects.filter(
            submission_type__event=sender
        ).prefetch_related("answers__question", "answers__options")
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
    else:
        # Later wizard steps (questions) no longer show the type field; it is
        # in the wizard's session data from the first step
        info = (
            request.session.get("cfp", {})
            .get(match.kwargs.get("tmpid", ""), {})
            .get("data", {})
            .get("info", {})
        )
        current = info.get("submission_type") or sender.cfp.default_type_id or ""
    return json_script(fixed, "fixed-sessions-data") + format_html(
        '<meta name="fixed-sessions" data-current-type="{}" data-notice="{}">'
        '<script defer src="{}"></script>',
        current,
        gettext(
            "This is a core session: the fields marked as fixed are set by "
            "the organisers."
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
