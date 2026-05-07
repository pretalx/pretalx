# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Exists, OuterRef, Q

from pretalx.orga.rules import can_view_speaker_names
from pretalx.person.models import SpeakerProfile
from pretalx.person.rules import is_reviewer
from pretalx.submission.enums import QuestionTarget
from pretalx.submission.models import Answer, Submission


def active_questions(
    event,
    *,
    target=QuestionTarget.SUBMISSION,
    track=None,
    submission_type=None,
    for_reviewers=False,
    skip_limited=False,
):
    """Active questions in a given answering scope.

    ``target=None`` includes every non-reviewer target.
    ``skip_limited=True`` drops any question restricted to specific tracks or
    submission types (and ignores ``track`` / ``submission_type``).
    """
    queryset = event.questions(manager="all_objects").filter(active=True)
    if target:
        queryset = queryset.filter(target=target)
    else:
        queryset = queryset.exclude(target=QuestionTarget.REVIEWER)
    if skip_limited:
        queryset = queryset.filter(tracks__isnull=True, submission_types__isnull=True)
    else:
        if track:
            queryset = queryset.filter(Q(tracks__in=[track]) | Q(tracks__isnull=True))
        if submission_type:
            queryset = queryset.filter(
                Q(submission_types__in=[submission_type])
                | Q(submission_types__isnull=True)
            )
    if for_reviewers:
        queryset = queryset.filter(is_visible_to_reviewers=True)
    return (
        queryset.select_related("event")
        .prefetch_related("options")
        .order_by("-target", "position", "id")
    )


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


def filter_submissions_by_question(
    qs, *, question=None, answer=None, option=None, unanswered=False
):
    """Filter a submission queryset by their answers to a question.

    ``option`` and ``answer`` privilege a positive match (returning
    submissions whose answer matches). ``unanswered=True`` is honoured
    only when neither is set, returning submissions with no answer to
    the question. Without a ``question``, the queryset is returned
    unchanged.
    """
    if not question:
        return qs
    answers = Answer.objects.filter(submission_id=OuterRef("pk"), question_id=question)
    if option:
        return qs.filter(Exists(answers.filter(options=option)))
    if answer:
        return qs.filter(Exists(answers.filter(answer__exact=answer)))
    if unanswered:
        return qs.filter(~Exists(answers))
    return qs


def count_missing_answers(question, *, filter_speakers=None, filter_talks=None):
    """How many answers are missing for ``question``.

    Only meaningful for submission and speaker questions; reviewer questions
    return ``0``. Pass ``filter_speakers`` or ``filter_talks`` (querysets) to
    restrict the scope.
    """
    answers = question.answers.all()
    filter_talks = filter_talks or Submission.objects.none()
    filter_speakers = filter_speakers or SpeakerProfile.objects.none()
    if filter_speakers or filter_talks:
        answers = answers.filter(
            Q(speaker__in=filter_speakers) | Q(submission__in=filter_talks)
        )
    answer_count = answers.count()
    if question.target == QuestionTarget.SUBMISSION:
        submissions = filter_talks or question.event.submissions.all()
        return max(submissions.count() - answer_count, 0)
    if question.target == QuestionTarget.SPEAKER:
        speakers = filter_speakers or question.event.submitters
        return max(speakers.count() - answer_count, 0)
    return 0


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


def answers_for_speaker(speaker):
    """All answers given by a speaker on their event.

    Includes both speaker-target answers (given for the speaker themselves)
    and submission-target answers on submissions they speak at, ordered by
    question position for stable rendering.
    """
    return Answer.objects.filter(
        Q(submission__in=speaker.submissions.all()) | Q(speaker=speaker)
    ).order_by("question__position")


def public_answers_for_submission(submission):
    """Public-facing submission answers, filtered to the submission's track and
    submission type.

    Honours per-question track/submission-type restrictions: questions limited
    to other tracks or types are dropped. Used by the public talk page.
    """
    qs = submission.answers.filter(
        Q(question__submission_types__in=[submission.submission_type])
        | Q(question__submission_types__isnull=True),
        question__is_public=True,
        question__event=submission.event,
        question__target=QuestionTarget.SUBMISSION,
    )
    if submission.track:
        qs = qs.filter(
            Q(question__tracks__in=[submission.track])
            | Q(question__tracks__isnull=True)
        )
    return qs.select_related("question").order_by("question__position")
