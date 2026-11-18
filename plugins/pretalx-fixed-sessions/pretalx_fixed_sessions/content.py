from contextlib import contextmanager
from contextvars import ContextVar

from django.db.models import Q
from django_scopes import scope

PLUGIN = "pretalx_fixed_sessions"


def is_active(event):
    return PLUGIN in event.plugin_list


def apply_to(submission):
    """Overwrite the proposal's content with its session type's fixed content.
    Changes the instance only; returns whether anything changed."""
    from .models import FixedSession

    if not submission.submission_type_id:
        return False
    fixed = FixedSession.objects.filter(
        submission_type_id=submission.submission_type_id
    ).first()
    if not fixed or not is_active(submission.event):
        return False
    changed = False
    for field, value in fixed.values().items():
        if getattr(submission, field) != value:
            setattr(submission, field, value)
            changed = True
    return changed


def apply_to_existing(fixed):
    """Write the fixed content and answers to every proposal of its session
    type, drafts and deleted ones included. Returns the number of proposals
    whose title, abstract, description, track or recording choice changed."""
    from pretalx.submission.models import Submission

    event = fixed.submission_type.event
    if not is_active(event):
        return 0
    values = fixed.values()
    # A negated lookup on a nullable column also matches NULL rows
    differs = Q()
    for field, value in values.items():
        differs |= ~Q(**{field: value})
    with scope(event=event):
        proposals = Submission.all_objects.filter(submission_type=fixed.submission_type)
        # QuerySet.update skips Submission.save(), so the pre_save receiver
        # doesn't run again for each row
        count = proposals.filter(differs).update(**values)
        for submission in proposals:
            apply_answers(submission)
    return count


# Set while this module writes answers, so the Answer receivers don't react
# to our own changes
_writing = ContextVar("fixed_sessions_writing", default=False)


def is_writing():
    return _writing.get()


@contextmanager
def _writing_answers():
    token = _writing.set(True)
    try:
        yield
    finally:
        _writing.reset(token)


def apply_answers(submission, question_id=None):
    """Make the proposal's answers to the core session's questions match the
    fixed answers (only the given question, if any). Questions without a
    fixed answer are left to the speaker."""
    from pretalx.submission.models import Answer, QuestionVariant

    from .models import FixedAnswer

    if not submission.pk or not submission.submission_type_id:
        return
    fixed_answers = FixedAnswer.objects.filter(
        fixed_session__submission_type_id=submission.submission_type_id
    ).select_related("question")
    if question_id is not None:
        fixed_answers = fixed_answers.filter(question_id=question_id)
    fixed_answers = list(fixed_answers.prefetch_related("options"))
    if not fixed_answers or not is_active(submission.event):
        return
    with scope(event=submission.event), _writing_answers():
        for fixed in fixed_answers:
            question = fixed.question
            existing = Answer.objects.filter(submission=submission, question=question)
            # pretalx stores "no" to a yes/no question as no answer at all
            if question.variant == QuestionVariant.BOOLEAN and fixed.answer != "True":
                existing.delete()
                continue
            options = {option.pk for option in fixed.options.all()}
            answer = existing.first()
            if answer is None:
                answer = Answer.objects.create(
                    question=question, submission=submission, answer=fixed.answer
                )
            elif answer.answer != fixed.answer:
                Answer.objects.filter(pk=answer.pk).update(answer=fixed.answer)
            is_choice = question.variant in (
                QuestionVariant.CHOICES,
                QuestionVariant.MULTIPLE,
            )
            if (
                is_choice
                and set(answer.options.values_list("pk", flat=True)) != options
            ):
                answer.options.set(options)
