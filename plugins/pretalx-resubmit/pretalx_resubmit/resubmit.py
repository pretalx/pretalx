"""Copying a speaker's proposal from one event into another of the same organiser."""

from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction
from django_scopes import scopes_disabled

from pretalx.submission.domain.submission import (
    available_submission_types_for_submitter,
    available_tracks_for_submitter,
    create_submission,
)
from pretalx.submission.enums import SubmissionStates
from pretalx.submission.models import Submission

from .models import Resubmission

# Content the speaker wrote; everything else (tags, reviews, schedule, internal
# notes, featured status) belongs to the original event's organisers.
COPIED_FIELDS = ("title", "abstract", "description", "notes", "do_not_record")


def _queryset(result):
    # pretalx 2026.2 returns the queryset; later versions return
    # (queryset, whether an access code determined it)
    return result[0] if isinstance(result, tuple) else result


def submission_types_for(event):
    """Session types a speaker without an access code can pick right now."""
    return _queryset(available_submission_types_for_submitter(event))


def tracks_for(event):
    """Tracks a speaker without an access code can pick."""
    return _queryset(available_tracks_for_submitter(event))


def can_resubmit_to(event):
    """Whether the event's CfP currently takes proposals without an access code."""
    if not event.cfp.is_open or not submission_types_for(event).exists():
        return False
    return not (
        event.cfp.require_track
        and event.has_active_tracks
        and not tracks_for(event).exists()
    )


def eligible_sources(event, user):
    """The user's proposals in the organiser's other events that were not yet
    resubmitted to ``event``, newest event first. Drafts are left out."""
    if user.is_anonymous:
        return []
    with scopes_disabled():
        already = Resubmission.objects.filter(
            submission__event=event, source__isnull=False
        ).values("source_id")
        return list(
            Submission.objects.filter(
                event__organiser_id=event.organiser_id, speakers__user=user
            )
            .exclude(event=event)
            .exclude(pk__in=already)
            .select_related("event", "submission_type", "track")
            .distinct()
            .order_by("-event__date_from", "title")
        )


def _copy_profile(user, *, source_event, event):
    """Fill the speaker's profile for ``event`` from their profile in the
    original event, where it is still empty."""
    source_profile = user.get_speaker(source_event, create=False)
    profile = user.get_speaker(event)
    if not source_profile:
        return
    changed = []
    if not profile.biography and source_profile.biography:
        profile.biography = source_profile.biography
        changed.append("biography")
    if not profile.profile_picture_id and source_profile.profile_picture_id:
        profile.profile_picture_id = source_profile.profile_picture_id
        changed.append("profile_picture")
    if changed:
        profile.save(update_fields=changed)


def resubmit(source, *, event, user, submission_type, track=None, content_locale=None):
    """Create a submitted copy of ``source`` in ``event`` with ``user`` as its
    only speaker. Co-speakers are not copied: they have to be invited again,
    so nobody is added to an event without agreeing to it."""
    with scopes_disabled(), transaction.atomic():
        submission = Submission(
            event=event,
            state=SubmissionStates.SUBMITTED,
            submission_type=submission_type,
            track=track,
            content_locale=content_locale or source.content_locale,
            **{field: getattr(source, field) for field in COPIED_FIELDS},
        )
        _copy_profile(user, source_event=source.event, event=event)
        submission = create_submission(
            submission=submission, user=user, speakers=[user], send_initial_mails=True
        )
        if source.image:
            # Saved after creation: the upload path contains the new proposal's code
            with source.image.open("rb") as image:
                submission.image.save(
                    Path(source.image.name).name, ContentFile(image.read()), save=True
                )
            submission.process_image("image")
        Resubmission.objects.create(submission=submission, source=source)
        submission.log_action(
            "pretalx_resubmit.resubmitted",
            person=user,
            data={
                "source_event": source.event.slug,
                "source_code": source.code,
                "source_title": source.title,
            },
        )
    return submission
