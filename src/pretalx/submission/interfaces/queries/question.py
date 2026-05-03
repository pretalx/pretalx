# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Q

from pretalx.orga.rules import can_view_speaker_names
from pretalx.person.rules import is_reviewer
from pretalx.submission.models import Answer, QuestionTarget


def questions_for_user(event, user):
    """Questions the user can see, with team-access filtering.

    A reviewer without submission edit perms is treated as a reviewer here
    regardless of any other perms (e.g. event settings) they may also hold,
    so they never see questions hidden from reviewers in review/listing views.
    """
    restricted_reviewer = (
        not user.is_anonymous
        and not user.has_perm("submission.orga_update_submission", event)
        and is_reviewer(user, event)
    )
    if restricted_reviewer and can_view_speaker_names(user, event):
        queryset = event.questions(manager="all_objects").filter(
            Q(is_visible_to_reviewers=True) | Q(target=QuestionTarget.REVIEWER),
            active=True,
        )
    elif restricted_reviewer:
        # Anonymised review phase: reviewers see only public questions
        queryset = event.questions.all().filter(is_public=True)
    elif user.has_perm("submission.update_question", event):
        # Organisers with edit permissions can see everything
        queryset = event.questions(manager="all_objects").all()
    elif user.has_perm("submission.orga_list_question", event):
        # Other team members can either view all active questions
        # or only questions open to reviewers
        queryset = event.questions(manager="all_objects").all()
    elif user.has_perm("submission.list_question", event):
        # Anonymous and low-perm users see public questions only
        queryset = event.questions.all().filter(is_public=True)
    else:
        return event.questions.none()

    if user.is_anonymous:
        team_filter = Q(limit_teams__isnull=True)
    else:
        team_filter = Q(limit_teams__isnull=True) | Q(limit_teams__in=user.teams.all())
    return queryset.filter(team_filter).select_related("event", "event__cfp").distinct()


def answers_for_user(event, user):
    """Answers to questions the user can see, with related fields prefetched.

    Sites that already have a constrained Answer queryset (e.g. a submission's
    own answers) should filter on ``question__in=questions_for_user(...)``
    directly instead.
    """
    return (
        Answer.objects.filter(question__in=questions_for_user(event, user))
        .select_related("question", "question__event", "submission", "speaker")
        .prefetch_related("options")
    )
