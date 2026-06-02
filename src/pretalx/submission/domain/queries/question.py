# SPDX-FileCopyrightText: 2025-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.db.models import Count, Exists, OuterRef, Q

from pretalx.orga.rules import can_view_speaker_names
from pretalx.person.models import SpeakerProfile
from pretalx.person.rules import is_reviewer
from pretalx.submission.enums import QuestionTarget, QuestionVariant
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
        queryset = event.questions.filter(is_public=True)
    elif user.has_perm("submission.update_question", event):
        # Organisers with edit permissions can see everything
        queryset = event.questions(manager="all_objects").all()
    elif user.has_perm("submission.orga_list_question", event):
        # Other team members can either view all active questions
        # or only questions open to reviewers
        queryset = event.questions(manager="all_objects").all()
    elif user.has_perm("submission.list_question", event):
        # Anonymous and low-perm users see public questions only
        queryset = event.questions.filter(is_public=True)
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


def missing_questions_for_speaker(*, speaker, submissions, questions):
    """Questions ``speaker`` hasn't fully answered for ``submissions``."""
    speaker_submissions = list(submissions.filter(speakers=speaker))
    submission_questions = [
        q for q in questions if q.target == QuestionTarget.SUBMISSION
    ]
    speaker_questions = [q for q in questions if q.target == QuestionTarget.SPEAKER]

    missing = []
    if submission_questions and speaker_submissions:
        answers_by_pair = {
            (a.question_id, a.submission_id): a
            for a in Answer.objects.filter(
                question__in=submission_questions, submission__in=speaker_submissions
            )
            .select_related("question")
            .prefetch_related("options")
        }
        for question in submission_questions:
            for submission in speaker_submissions:
                answer = answers_by_pair.get((question.pk, submission.pk))
                if not answer or not answer.is_answered:
                    missing.append(question)

    if speaker_questions:
        answers_by_question = {
            a.question_id: a
            for a in Answer.objects.filter(
                question__in=speaker_questions, speaker=speaker
            )
            .select_related("question")
            .prefetch_related("options")
        }
        for question in speaker_questions:
            answer = answers_by_question.get(question.pk)
            if not answer or not answer.is_answered:
                missing.append(question)
    return missing


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


def question_answer_summary(*, question, talks, speakers):
    """Counts and grouped answers for ``question`` over a filtered scope."""
    answers = (
        question.answers.filter(Q(speaker__in=speakers) | Q(submission__in=talks))
        .order_by("pk")
        .distinct()
    )
    if question.variant in (QuestionVariant.CHOICES, QuestionVariant.MULTIPLE):
        grouped_answers = (
            answers.order_by("options")
            .values("options", "options__answer")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
    elif question.variant == QuestionVariant.FILE:
        grouped_answers = [{"answer": answer, "count": 1} for answer in answers]
    else:
        grouped_answers = (
            answers.order_by("answer")
            .values("answer")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
    return {
        "answer_count": answers.count(),
        "missing_answers": count_missing_answers(
            question, filter_speakers=speakers, filter_talks=talks
        ),
        "grouped_answers": grouped_answers,
    }


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


def public_answers_for_speaker(speaker):
    """Public-facing speaker-target answers for ``speaker``'s profile page.

    Mirrors :func:`public_answers_for_submission`: only public, speaker-target
    answers on the speaker's event, ordered by question position.
    """
    return (
        speaker.answers.filter(
            question__is_public=True,
            question__event=speaker.event,
            question__target=QuestionTarget.SPEAKER,
        )
        .select_related("question")
        .order_by("question__position")
    )


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
