from datetime import timedelta

import rules
from django.utils.timezone import now

from pretalx.person.permissions import (
    can_change_submissions, is_administrator, is_reviewer,
)
from pretalx.submission.permissions import (
    can_be_reviewed, can_view_all_reviews, can_view_reviews,
    is_review_author, reviewer_can_change_submissions,
)


@rules.predicate
def can_change_event_settings(user, obj):
    event = getattr(obj, 'event', None)
    if not user or user.is_anonymous or not obj or not event:
        return False
    return user.is_administrator or event.teams.filter(members__in=[user], can_change_event_settings=True).exists()


@rules.predicate
def can_change_organiser_settings(user, obj):
    event = getattr(obj, 'event', None)
    if event:
        obj = event.organiser
    return (
        user.is_administrator
        or user.teams.filter(organiser=obj, can_change_organiser_settings=True).exists()
    )


@rules.predicate
def can_change_any_organiser_settings(user, obj):
    return not user.is_anonymous and (
        user.is_administrator
        or user.teams.filter(can_change_organiser_settings=True).exists()
    )


@rules.predicate
def can_create_events(user, obj):
    return user.is_administrator or user.teams.filter(can_create_events=True).exists()


@rules.predicate
def can_change_teams(user, obj):
    from pretalx.event.models import Organiser, Team

    if isinstance(obj, Team):
        obj = obj.organiser
    if isinstance(obj, Organiser):
        return user.teams.filter(organiser=obj, can_change_teams=True).exists()
    event = getattr(obj, 'event', None)
    if not user or user.is_anonymous or not obj or not event:
        return False
    return user.is_administrator or event.teams.filter(members__in=[user], can_change_teams=True).exists()


@rules.predicate
def reviews_are_open(user, obj):
    event = obj.event
    return event.active_review_phase and event.active_review_phase.can_review


@rules.predicate
def can_edit_mail(user, obj):
    return hasattr(obj, 'sent') and obj.sent is None


@rules.predicate
def can_mark_speakers_arrived(user, obj):
    event = obj.event
    return (event.date_from - timedelta(days=1)) <= now().date() <= event.date_to


@rules.predicate
def is_event_over(user, obj):
    event = obj.event
    return event.date_to < now().date()


@rules.predicate
def can_view_speaker_names(user, obj):
    event = obj.event
    return event.active_review_phase and event.active_review_phase.can_see_speaker_names


rules.add_perm('orga.view_orga_area', can_change_submissions | is_reviewer)
rules.add_perm('orga.change_settings', can_change_event_settings)
rules.add_perm('orga.change_organiser_settings', can_change_organiser_settings)
rules.add_perm('orga.view_organisers', can_change_any_organiser_settings)
rules.add_perm('orga.change_teams', is_administrator | can_change_teams)
rules.add_perm('orga.view_submission_cards', can_change_submissions)
rules.add_perm('orga.edit_cfp', can_change_event_settings)
rules.add_perm('orga.view_question', can_change_submissions)
rules.add_perm('orga.edit_question', can_change_event_settings)
rules.add_perm('orga.remove_question', can_change_event_settings)
rules.add_perm('orga.view_submission_type', can_change_submissions)
rules.add_perm('orga.edit_submission_type', can_change_event_settings)
rules.add_perm('orga.remove_submission_type', can_change_event_settings)
rules.add_perm('orga.view_tracks', can_change_submissions)
rules.add_perm('orga.view_track', can_change_submissions)
rules.add_perm('orga.edit_track', can_change_event_settings)
rules.add_perm('orga.remove_track', can_change_event_settings)
rules.add_perm('orga.view_mails', can_change_submissions)
rules.add_perm('orga.send_mails', can_change_submissions)
rules.add_perm('orga.edit_mails', can_change_submissions & can_edit_mail)
rules.add_perm('orga.purge_mails', can_change_submissions)
rules.add_perm('orga.view_mail_templates', can_change_submissions)
rules.add_perm('orga.edit_mail_templates', can_change_submissions)
rules.add_perm('orga.view_review_dashboard', can_change_submissions | is_reviewer)
rules.add_perm('orga.view_reviews', can_change_submissions | (is_reviewer & can_view_reviews))
rules.add_perm('orga.view_all_reviews', can_change_submissions | (is_reviewer & can_view_all_reviews))
rules.add_perm('orga.perform_reviews', is_reviewer & reviews_are_open)
rules.add_perm('orga.remove_review', is_administrator | (is_review_author & can_be_reviewed))
rules.add_perm('orga.view_schedule', can_change_submissions)
rules.add_perm('orga.release_schedule', can_change_submissions)
rules.add_perm('orga.edit_schedule', can_change_submissions)
rules.add_perm('orga.schedule_talk', can_change_submissions)
rules.add_perm('orga.view_room', can_change_submissions)
rules.add_perm('orga.edit_room', can_change_submissions)
rules.add_perm('orga.view_speakers', can_change_submissions | (is_reviewer & can_view_speaker_names))
rules.add_perm('orga.view_speaker', can_change_submissions | (is_reviewer & can_view_speaker_names))
rules.add_perm('orga.change_speaker', can_change_submissions)
rules.add_perm('orga.view_submissions', can_change_submissions | is_reviewer)
rules.add_perm('orga.create_submission', can_change_submissions)
rules.add_perm('orga.change_submissions', can_change_submissions)
rules.add_perm('orga.change_submission_state', can_change_submissions | (is_reviewer & reviewer_can_change_submissions))
rules.add_perm('orga.view_information', can_change_submissions)
rules.add_perm('orga.change_information', can_change_event_settings)
rules.add_perm('orga.create_events', can_create_events)
rules.add_perm('orga.change_plugins', is_administrator)
rules.add_perm('orga.mark_speakers_arrived', can_change_submissions & can_mark_speakers_arrived)
rules.add_perm('orga.see_speakers_arrival', can_change_submissions & is_event_over)
