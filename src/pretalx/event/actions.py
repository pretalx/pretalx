from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from pretalx.event.models import Event
from pretalx.mail.default_templates import (
    ACCEPT_TEXT, ACK_TEXT, GENERIC_SUBJECT, QUESTION_SUBJECT,
    QUESTION_TEXT, REJECT_TEXT, UPDATE_SUBJECT, UPDATE_TEXT,
)
from pretalx.mail.models import MailTemplate
from pretalx.schedule.models import Schedule
from pretalx.submission.models import CfP, ReviewPhase, SubmissionType


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
