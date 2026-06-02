# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import datetime as dt

from dateutil.relativedelta import relativedelta
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import F, Q
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from django_scopes import scopes_disabled

from pretalx.common.models import ActivityLog
from pretalx.event.models import Event
from pretalx.mail.domain.template import mail_template_by_role
from pretalx.mail.enums import MailTemplateRoles
from pretalx.orga.signals import activate_event as activate_event_signal
from pretalx.orga.signals import event_copy_data
from pretalx.person.models import SpeakerProfile
from pretalx.schedule.models import Availability, Schedule, TalkSlot
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

IMAGE_FIELDS = ("logo", "header_image", "og_image")
DATE_FIELDS = ("date_from", "date_to")


@transaction.atomic
def create_event(*, organiser, locales, user=None, **fields):
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


@transaction.atomic
def post_create_event(event, *, user, deadline=None, display_settings=None):
    if deadline is not None:
        event.cfp.deadline = deadline.replace(tzinfo=event.tz)
        event.cfp.save()

    if display_settings:
        changed = False
        for key, value in display_settings.items():
            if value:
                event.display_settings[key] = value
                changed = True
        if changed:
            event.save(update_fields=["display_settings"])

    if event.logo:
        event.process_image("logo")

    has_control_rights = user.teams.filter(
        organiser=event.organiser,
        all_events=True,
        can_change_event_settings=True,
        can_change_submissions=True,
    ).exists()
    if not has_control_rights:
        team = event.organiser.teams.create(
            name=_("Team {event.name}").format(event=event),
            can_change_event_settings=True,
            can_change_submissions=True,
        )
        team.members.add(user)
        team.limit_events.add(event)


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
    if event.review_phases.exists():
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
    if event.score_categories.exists():
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


def _make_naive(moment):
    return dt.datetime(  # noqa: DTZ001  -- intentionally naive; strips tzinfo so we can compare apparent times
        year=moment.year,
        month=moment.month,
        day=moment.day,
        hour=moment.hour,
        minute=moment.minute,
    )


def _move_slots(event, delta, *, past=False):
    if past:
        talk_queryset = TalkSlot.objects.filter(schedule__event=event)
    else:
        talk_queryset = event.wip_schedule.talks
    for key in ("start", "end"):
        filt = {f"{key}__isnull": False}
        update = {key: F(key) + delta}
        talk_queryset.filter(**filt).update(**update)
        Availability.objects.filter(event=event).filter(**filt).update(**update)


def apply_date_edit(event, old_event):
    """React to an organiser editing the event's start/end date.

    Only affects the WIP schedule. Drops slots at the tail end if the event
    gets shorter.
    """
    if not event.wip_schedule.talks.filter(start__isnull=False).exists():
        return
    start_delta = event.date_from - old_event.date_from
    end_delta = event.date_to - old_event.date_to
    shortened = (event.date_to - event.date_from) < (
        old_event.date_to - old_event.date_from
    )

    if start_delta and end_delta:
        # The event was moved, and we will move all talks with it.
        _move_slots(event, start_delta)

    # Otherwise, the event got longer, no need to do anything.
    # We *could* move all talks towards the new start date, but I'm
    # not convinced that this is the actual use case.
    # I think it's more likely that people add a new day to the start.
    if shortened:
        # The event was shortened, de-schedule all talks outside the range
        event.wip_schedule.talks.filter(
            Q(start__date__gt=event.date_to) | Q(start__date__lt=event.date_from)
        ).update(start=None, end=None, room=None)
        Availability.objects.filter(
            Q(end__date__gt=event.date_to) | Q(start__date__lt=event.date_from),
            event=event,
        ).delete()


def move_full_event(event, new_start_date):
    """Relocate the entire event so its start date lands on ``new_start_date``.
    Includes historical data, primarily used to shift demo events.
    Organiser-triggered changes go through ``apply_date_edit``.
    """
    days_delta = new_start_date - event.date_from
    if not days_delta.days:
        return
    event.date_from += days_delta
    event.date_to += days_delta
    event.save()
    _move_slots(event, days_delta, past=True)


def apply_timezone_edit(event, old_event):
    """React to an organiser changing the event's timezone, preserving the
    apparent local time of every scheduled session. Includes historical data.
    """
    first_slot = event.wip_schedule.talks.filter(start__isnull=False).first()
    if not first_slot:
        return

    old_start = _make_naive(first_slot.start.astimezone(old_event.tz))
    new_start = _make_naive(first_slot.start.astimezone(event.tz))

    delta = old_start - new_start
    if delta:
        _move_slots(event, delta, past=True)


@transaction.atomic
def apply_event_changes(event, changed_fields, *, custom_css_text=None):
    """The event must already have its new values assigned but not yet persisted."""
    changed = set(changed_fields)
    old_event = Event.objects.get(pk=event.pk) if event.pk else None

    if old_event is not None and any(field in changed for field in DATE_FIELDS):
        apply_date_edit(event, old_event)
    if old_event is not None and "timezone" in changed:
        apply_timezone_edit(event, old_event)

    event.save()

    for image_field in IMAGE_FIELDS:
        if image_field in changed:
            event.process_image(image_field)
    if custom_css_text is not None and "custom_css_text" in changed:
        event.custom_css.save(event.slug + ".css", ContentFile(custom_css_text))


def activate_event(event, *, user, request=None):
    """Returns a ``(exceptions, extra_messages)`` tuple. ``exceptions`` is
    non-empty iff activation was vetoed; ``extra_messages`` is a list of
    plain-string plugin responses to display alongside the success.
    """
    responses = activate_event_signal.send_robust(event, request=request)
    exceptions = [
        response[1] for response in responses if isinstance(response[1], Exception)
    ]
    if exceptions:
        return exceptions, []
    event.is_public = True
    event.save()
    event.log_action("pretalx.event.activate", person=user, orga=True, data={})
    extra_messages = [
        response[1] for response in responses if isinstance(response[1], str)
    ]
    return [], extra_messages


def deactivate_event(event, *, user):
    event.is_public = False
    event.save()
    event.log_action("pretalx.event.deactivate", person=user, orga=True, data={})


def shred_event(event, person=None):
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
