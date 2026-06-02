# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import rules
from django.core.exceptions import ObjectDoesNotExist

from pretalx.person.rules import is_reviewer
from pretalx.submission.enums import SubmissionStates


@rules.predicate
def reviewer_can_create_tags(user, obj):
    event = obj.event
    return bool(
        event.active_review_phase
        and event.active_review_phase.can_tag_submissions == "create_tags"
    )


@rules.predicate
def reviewer_can_change_submissions(user, obj):
    return bool(
        obj.event.active_review_phase
        and obj.event.active_review_phase.can_change_submission_state
    )


@rules.predicate
def reviewer_can_change_tags(user, obj):
    event = obj.event
    return bool(
        event.active_review_phase
        and event.active_review_phase.can_tag_submissions == "use_tags"
    )


@rules.predicate
def orga_can_change_submissions(user, obj):
    event = getattr(obj, "event", None)
    if not user or user.is_anonymous or not obj or not event:
        return False
    if user.is_administrator:
        return True
    return "can_change_submissions" in user.get_permissions_for_event(event)


orga_can_view_submissions = orga_can_change_submissions | is_reviewer


@rules.predicate
def is_cfp_open(user, obj):
    event = getattr(obj, "event", None)
    return event and event.is_public and event.cfp.is_open


@rules.predicate
def use_tracks(user, obj):
    event = obj.event
    return event.get_feature_flag("use_tracks")


@rules.predicate
def is_speaker(user, obj):
    obj = getattr(obj, "submission", obj)
    if not obj or obj._state.adding:
        return False
    return any(s.user_id == user.id for s in obj.speakers.all())


@rules.predicate
def can_be_withdrawn(user, obj):
    return obj and obj.state in (SubmissionStates.SUBMITTED, SubmissionStates.ACCEPTED)


@rules.predicate
def can_be_confirmed(user, obj):
    return obj and obj.state == SubmissionStates.ACCEPTED


@rules.predicate
def can_be_removed(user, obj):
    return obj and obj.state != SubmissionStates.DRAFT


@rules.predicate
def can_be_edited(user, obj):
    return obj and obj.editable


@rules.predicate
def can_request_speakers(user, submission):
    return (
        submission.state != SubmissionStates.DRAFT
        and submission.event.cfp.request_additional_speaker
    )


@rules.predicate
def reviews_are_open(user, obj):
    event = obj.event
    return bool(event.active_review_phase and event.active_review_phase.can_review)


@rules.predicate
def can_view_all_reviews(user, obj):
    event = obj.event
    return bool(
        event.active_review_phase
        and event.active_review_phase.can_see_other_reviews == "always"
    )


@rules.predicate
def can_view_reviewer_names(user, obj):
    event = obj.event
    return bool(
        event.active_review_phase and event.active_review_phase.can_see_reviewer_names
    )


@rules.predicate
def can_view_reviews(user, obj):
    if can_view_all_reviews(user, obj):
        return True
    phase = obj.event.active_review_phase
    submission = getattr(obj, "submission", obj)
    return bool(
        phase
        and phase.can_see_other_reviews == "after_review"
        and submission.reviews.filter(user=user).exists()
    )


@rules.predicate
def can_be_reviewed(user, obj):
    if not obj:
        return False
    obj = getattr(obj, "submission", obj)
    phase = obj.event.active_review_phase and obj.event.active_review_phase.can_review
    state = obj.state == SubmissionStates.SUBMITTED
    return bool(state and phase)


@rules.predicate
def has_reviewer_access(user, obj):
    if not user or user.is_anonymous:
        return False
    obj = getattr(obj, "submission", obj)
    try:
        event = getattr(obj, "event", None)
    except (AttributeError, ObjectDoesNotExist):
        return False
    if (
        not event
        or not event.active_review_phase
        or "is_reviewer" not in user.get_permissions_for_event(event)
    ):
        return False
    if event.active_review_phase.proposal_visibility == "all":
        reviewer_tracks = user.get_reviewer_tracks(event)
        if reviewer_tracks is None:
            return True
        return getattr(obj, "track_id", None) in reviewer_tracks
    return user in obj.assigned_reviewers.all()


@rules.predicate
def reviewer_can_change_submission_state(user, obj):
    from pretalx.submission.models import Submission  # noqa: PLC0415 -- predicate

    if not reviewer_can_change_submissions(user, obj):
        return False
    submission = getattr(obj, "submission", obj)
    if not isinstance(submission, Submission):
        return is_reviewer(user, obj)
    return has_reviewer_access(user, obj)


orga_or_reviewer_can_change_submission = (
    orga_can_change_submissions | reviewer_can_change_submission_state
)


@rules.predicate
def has_team_question_access(user, obj):
    from pretalx.submission.domain.queries.question import (  # noqa: PLC0415 -- predicate
        questions_for_user,
    )

    return questions_for_user(obj.event, user).filter(pk=obj.pk).exists()


@rules.predicate
def is_wip(user, obj):
    schedule = getattr(obj, "schedule", None) or obj
    return not schedule.version


@rules.predicate
def is_feedback_ready(user, obj):
    return obj.does_accept_feedback


@rules.predicate
def is_break(user, obj):
    return not obj.submission


@rules.predicate
def is_review_author(user, obj):
    return obj and obj.user == user


@rules.predicate
def is_comment_author(user, obj):
    return obj and obj.user == user


@rules.predicate
def submission_comments_active(user, obj):
    return obj.event.get_feature_flag("use_submission_comments")


def is_featured_visible(submission):
    """Would ``submission`` appear on its event's featured page?"""
    from pretalx.submission.domain.queries.submission import (  # noqa: PLC0415 -- predicate
        FEATURED_HIDDEN_STATES,
    )

    return bool(
        submission
        and submission.is_featured
        and submission.state not in FEATURED_HIDDEN_STATES
    )
