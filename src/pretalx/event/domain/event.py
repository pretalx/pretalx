# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from django_scopes import scopes_disabled

from pretalx.common.models import ActivityLog
from pretalx.mail.domain.template import mail_template_by_role
from pretalx.mail.enums import MailTemplateRoles
from pretalx.orga.signals import event_copy_data
from pretalx.person.models import SpeakerProfile
from pretalx.schedule.models import Schedule, TalkSlot
from pretalx.submission.models import (
    Answer,
    AnswerOption,
    CfP,
    Feedback,
    Question,
    Resource,
    ReviewPhase,
    ReviewScore,
    ReviewScoreCategory,
    Submission,
    SubmissionType,
)


@transaction.atomic
def create_event(*, organiser, locales, user=None, **fields):
    """Create an :class:`Event` for ``organiser``.

    ``locales`` is a sequence of language codes; it populates both
    ``locale_array`` and ``content_locale_array``. All other model
    fields are passed through verbatim. ``full_clean`` runs so field
    validators (slug regex / reserved-name check, primary-color regex)
    and ``Event.clean`` (slug lowercasing + uniqueness, date ordering)
    both apply even when callers bypass form validation — mirroring
    :func:`pretalx.person.domain.user.create_user`.
    """
    locale_array = ",".join(locales)
    event = organiser.events.model(
        organiser=organiser,
        locale_array=locale_array,
        content_locale_array=locale_array,
        **fields,
    )
    event.full_clean()
    event.save()
    initialise_event(event)
    if user is not None:
        event.log_action("pretalx.event.create", person=user, orga=True)
    return event


def _ensure_cfp(event):
    if hasattr(event, "cfp"):
        return
    default_type = SubmissionType.objects.filter(event=event).first()
    if not default_type:
        default_type = SubmissionType.objects.create(event=event, name="Talk")
    CfP.objects.create(event=event, default_type=default_type)


def _ensure_wip_schedule(event):
    if not event.schedules.filter(version__isnull=True).exists():
        Schedule.objects.create(event=event)


def _ensure_role_mail_templates(event):
    for role, __ in MailTemplateRoles.choices:
        mail_template_by_role(event, role)


def _ensure_review_phases(event):
    if event.review_phases.all().exists():
        return
    cfp_deadline = event.cfp.deadline
    review_end = event.datetime_from + relativedelta(months=3)
    ReviewPhase.objects.create(
        event=event,
        name=_("Review"),
        start=cfp_deadline,
        end=review_end,
        is_active=not cfp_deadline or cfp_deadline < now(),
    )
    ReviewPhase.objects.create(
        event=event,
        name=_("Selection"),
        start=review_end,
        is_active=False,
        can_review=False,
        can_see_other_reviews="always",
        can_change_submission_state=True,
    )


def _ensure_score_categories(event):
    if event.score_categories.all().exists():
        return
    category = ReviewScoreCategory.objects.create(
        event=event, name=str(pgettext_lazy("review score/rating", "Score"))
    )
    ReviewScore.objects.create(category=category, value=0, label=str(_("No")))
    ReviewScore.objects.create(category=category, value=1, label=str(_("Maybe")))
    ReviewScore.objects.create(category=category, value=2, label=str(_("Yes")))


@transaction.atomic
def initialise_event(event):
    """Build the supporting data a new event needs: a CfP, a WIP schedule,
    all mail templates, a review phases, and a default review score category.
    Idempotent.
    """
    _ensure_cfp(event)
    _ensure_wip_schedule(event)
    _ensure_role_mail_templates(event)
    _ensure_review_phases(event)
    _ensure_score_categories(event)


@scopes_disabled()
def copy_event_data(event, source, skip_attributes=None):
    """Copy configuration from ``source`` onto ``event`` in place.

    Dates are shifted based on the ``date_from`` delta. Triggers
    ``initialise_event`` to make sure the resulting event is complete.
    """
    delta = event.date_from - source.date_from

    clonable_attributes = [
        "locale",
        "locale_array",
        "primary_color",
        "timezone",
        "email",
        "plugins",
        "feature_flags",
        "display_settings",
        "review_settings",
        "content_locale_array",
        "landing_page_text",
        "featured_sessions_text",
    ]
    if skip_attributes:
        clonable_attributes = [
            attr for attr in clonable_attributes if attr not in skip_attributes
        ]
    for attribute in clonable_attributes:
        setattr(event, attribute, getattr(source, attribute))
    event.save()

    for extra_link in source.extra_links.all():
        extra_link.pk = None
        extra_link.event = event
        extra_link.save()

    event.mail_templates.all().delete()
    for mail_template in source.mail_templates.filter(is_auto_created=False):
        mail_template.pk = None
        mail_template.event = event
        mail_template.save()

    # Submission types need a bespoke loop: the target's CfP already
    # points at a freshly-created default type, which we have to swap
    # for the source's default before deleting the placeholder.
    event.submission_types.exclude(pk=event.cfp.default_type_id).delete()
    submission_type_map = {}
    for submission_type in source.submission_types.all():
        old_pk = submission_type.pk
        is_default = submission_type == source.cfp.default_type
        submission_type.pk = None
        submission_type.event = event
        submission_type.save()
        submission_type_map[old_pk] = submission_type
        if is_default:
            old_default = event.cfp.default_type
            event.cfp.default_type = submission_type
            event.cfp.save()
            old_default.delete(skip_log=True)

    track_map = {}
    for track in source.tracks.all():
        old_pk = track.pk
        track.pk = None
        track.event = event
        track.save()
        track_map[old_pk] = track

    if not event.rooms.exists():
        # Rooms own availabilities (FK), and we shift each availability
        # by the date delta — bespoke loop.
        for room in source.rooms.all():
            availabilities = list(room.availabilities.all())
            room.pk = None
            room.event = event
            room.save()
            for availability in availabilities:
                availability.pk = None
                availability.room = room
                availability.event = event
                availability.start += delta
                availability.end += delta
                availability.save()

    # Questions own options (FK) and have two m2m to remapped collections.
    question_map = {}
    for question in source.questions.all():
        old_pk = question.pk
        options = list(question.options.all())
        track_pks = list(question.tracks.values_list("pk", flat=True))
        type_pks = list(question.submission_types.values_list("pk", flat=True))
        question.pk = None
        question.event = event
        question.save()
        question.tracks.set([track_map[pk] for pk in track_pks])
        question.submission_types.set([submission_type_map[pk] for pk in type_pks])
        for option in options:
            option.pk = None
            option.question = question
            option.save()
        question_map[old_pk] = question

    information_map = {}
    for information in source.information.all():
        old_pk = information.pk
        track_pks = list(information.limit_tracks.values_list("pk", flat=True))
        type_pks = list(information.limit_types.values_list("pk", flat=True))
        information.pk = None
        information.event = event
        information.save()
        information.limit_tracks.set([track_map[pk] for pk in track_pks])
        information.limit_types.set([submission_type_map[pk] for pk in type_pks])
        information_map[old_pk] = information

    event.review_phases.all().delete()

    # Review phases are date-shifted and force-deactivated.
    for review_phase in source.review_phases.all():
        review_phase.pk = None
        review_phase.event = event
        review_phase.is_active = False
        if review_phase.start:
            review_phase.start += delta
        if review_phase.end:
            review_phase.end += delta
        review_phase.save()

    event.score_categories.all().delete()
    # Score categories own scores (FK) and have a tracks m2m.
    for score_category in source.score_categories.all():
        scores = list(score_category.scores.all())
        track_pks = list(score_category.limit_tracks.values_list("pk", flat=True))
        score_category.pk = None
        score_category.event = event
        score_category.save()
        score_category.limit_tracks.set([track_map[pk] for pk in track_pks])
        for score in scores:
            score.pk = None
            score.category = score_category
            score.save()

    for sett in source.settings._objects.all():  # noqa: SLF001 -- hierarkey internal
        if sett.value.startswith("file://"):
            continue
        sett.object = event
        sett.pk = None
        sett.save()
    event.settings.flush()

    for user_prefs in source.user_preferences.all():
        user_prefs.pk = None
        user_prefs.event = event
        user_prefs.save()

    event.cfp.copy_data_from(source.cfp, skip_attributes=skip_attributes)
    event_copy_data.send(
        sender=event,
        other=source.slug,
        question_map=question_map,
        track_map=track_map,
        submission_type_map=submission_type_map,
        speaker_information_map=information_map,
    )
    initialise_event(event)


def shred_event(event, person=None):
    """Irrevocably delete ``event`` and all dependent data."""
    ActivityLog.objects.create(
        person=person,
        action_type="pretalx.event.delete",
        content_object=event.organiser,
        is_orga_action=True,
        data={
            "slug": event.slug,
            "name": str(event.name),
            # We log the organiser because events and organisers are
            # often deleted together.
            "organiser": str(event.organiser.name),
        },
    )
    with transaction.atomic():
        deletion_order = [
            (event.logged_actions(), False),
            (event.mail_templates.all(), False),
            (event.queued_mails.all(), False),
            (event.cfp, False),
            (event.information.all(), True),
            (TalkSlot.objects.filter(schedule__event=event), False),
            (Feedback.objects.filter(talk__event=event), False),
            (Resource.objects.filter(submission__event=event), True),
            (Answer.objects.filter(question__event=event), True),
            (AnswerOption.objects.filter(question__event=event), False),
            (Question.all_objects.filter(event=event), False),
            (Submission.all_objects.filter(event=event), True),
            (event.tracks.all(), False),
            (event.tags.all(), False),
            (event.submission_types.all(), False),
            (event.schedules.all(), False),
            (SpeakerProfile.objects.filter(event=event), False),
            (event.rooms.all(), False),
            (ActivityLog.objects.filter(event=event), False),
            (event, False),
        ]

        for entry, detail in deletion_order:
            if detail:
                for obj in entry:
                    obj.delete()
            else:
                entry.delete()
