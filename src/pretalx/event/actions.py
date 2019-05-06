from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from pretalx.common.models import ActivityLog
from pretalx.event.models import Event
from pretalx.mail.default_templates import (
    ACCEPT_TEXT, ACK_TEXT, GENERIC_SUBJECT, QUESTION_SUBJECT,
    QUESTION_TEXT, REJECT_TEXT, UPDATE_SUBJECT, UPDATE_TEXT,
)
from pretalx.mail.models import MailTemplate
from pretalx.person.models import SpeakerProfile
from pretalx.schedule.models import Schedule, TalkSlot
from pretalx.submission.models import (
    Answer, AnswerOption, CfP, Feedback, Question,
    Resource, ReviewPhase, SubmissionType,
)


@transaction.atomic
def build_initial_data(event: Event):
    """Builds all required related data for an event.

    Generates mail templates, CfP, review phases, and a default submission
    type."""
    if not hasattr(event, "cfp"):
        sub_type = SubmissionType.objects.filter(event=event).first()
        if not sub_type:
            sub_type = SubmissionType.objects.create(event=event, name="Talk")
        CfP.objects.create(event=event, default_type=sub_type)

    Schedule.objects.get_or_create(event=event, version=None)
    event.accept_template = event.accept_template or MailTemplate.objects.create(
        event=event, subject=GENERIC_SUBJECT, text=ACCEPT_TEXT
    )
    event.ack_template = event.ack_template or MailTemplate.objects.create(
        event=event, subject=GENERIC_SUBJECT, text=ACK_TEXT
    )
    event.reject_template = event.reject_template or MailTemplate.objects.create(
        event=event, subject=GENERIC_SUBJECT, text=REJECT_TEXT
    )
    event.update_template = event.update_template or MailTemplate.objects.create(
        event=event, subject=UPDATE_SUBJECT, text=UPDATE_TEXT
    )
    event.question_template = event.question_template or MailTemplate.objects.create(
        event=event, subject=QUESTION_SUBJECT, text=QUESTION_TEXT
    )

    if not event.review_phases.all().exists():
        cfp_deadline = event.cfp.deadline
        r = ReviewPhase.objects.create(
            event=event,
            name=_("Review"),
            start=cfp_deadline,
            end=event.datetime_from - relativedelta(months=-3),
            is_active=bool(not cfp_deadline or cfp_deadline < now()),
            position=0,
        )
        ReviewPhase.objects.create(
            event=event,
            name=_("Selection"),
            start=r.end,
            is_active=False,
            position=1,
            can_review=False,
            can_see_other_reviews="always",
            can_change_submission_state=True,
        )
    event.save()


def delete_mail_templates(event: Event):
    """Deletes all mail templates on an event, including special cases."""
    for template in event.template_names:
        setattr(event, template, None)
    event.save()
    event.mail_templates.all().delete()


@transaction.atomic
def copy_data_from(other_event: Event, event: Event):
    """Copies all configuration from the first argument to the second."""
    protected_settings = ["custom_domain", "display_header_data"]
    has_cfp = hasattr(event, "cfp")
    delete_mail_templates(event)
    if has_cfp:
        event.submission_types.exclude(pk=event.cfp.default_type_id).delete()
        old_default = event.cfp.default_type
    else:
        event.submission_types.all().delete()
        other_event.cfp.pk = None
        other_event.cfp.event = event
        other_event.cfp.save()

    for template in event.template_names:
        new_template = getattr(other_event, template)
        new_template.pk = None
        new_template.event = event
        new_template.save()
        setattr(event, template, new_template)

    for submission_type in other_event.submission_types.all():
        is_default = submission_type == other_event.cfp.default_type
        submission_type.pk = None
        submission_type.event = event
        submission_type.save()
        if is_default:
            event.cfp.default_type = submission_type
            event.cfp.save()
            if has_cfp:
                old_default.delete()

    for setting in other_event.settings._objects.all():
        if setting.value.startswith("file://") or setting.key in protected_settings:
            continue
        setting.object = event
        setting.pk = None
        setting.save()
    build_initial_data(event)  # make sure we get a functioning event


@transaction.atomic
def shred_event(event: Event):
    """Irrevocably deletes an event and all related data."""
    deletion_order = [
        event.logged_actions(),
        event.queued_mails.all(),
        event.cfp,
        event.mail_templates.all(),
        event.information.all(),
        TalkSlot.objects.filter(schedule__event=event),
        Feedback.objects.filter(talk__event=event),
        Resource.objects.filter(submission__event=event),
        Answer.objects.filter(question__event=event),
        AnswerOption.objects.filter(question__event=event),
        Question.all_objects.filter(event=event),
        event.submissions(manager="all_objects").all(),
        event.submission_types.all(),
        event.schedules.all(),
        SpeakerProfile.objects.filter(event=event),
        event.rooms.all(),
        ActivityLog.objects.filter(event=event),
        event,
    ]
    delete_mail_templates(event)
    for entry in deletion_order:
        entry.delete()
