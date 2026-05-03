# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.core.files.uploadedfile import UploadedFile

from pretalx.submission.enums import QuestionVariant


def _is_empty(value):
    # We allow numerical zero, but discard all other empty values
    return value == "" or value is None or value is False


def save_answer(*, question, value, target_object, existing=None):
    """Persist a value as the Answer to a question for one target object.

    ``target_object`` is the parent object the question is being answered
    for: a ``Submission``, ``SpeakerProfile``, or ``Review``, matching
    ``question.target``.

    ``value`` is a typed value matching the question variant: an
    ``AnswerOption`` for ``CHOICES``, an iterable of options for
    ``MULTIPLE``, an ``UploadedFile`` (or unchanged file path) for ``FILE``,
    a primitive otherwise.

    If ``existing`` is given and ``value`` is empty, the answer is removed.
    Returns the saved ``Answer`` instance, or ``None`` when the answer was
    deleted or no answer was needed.
    """
    if existing and _is_empty(value):
        existing.delete(skip_log=True)
        return None

    if _is_empty(value):
        return None

    answer = existing or question.answers.model(question=question)
    answer.target_object = target_object
    _set_value(question, answer, value)
    answer.save()
    return answer


def _set_value(question, answer, value):
    if question.variant == QuestionVariant.CHOICES:
        _set_choice_options(answer, [value] if value else [])
    elif question.variant == QuestionVariant.MULTIPLE:
        _set_choice_options(answer, list(value or ()))
    elif question.variant == QuestionVariant.FILE:
        if isinstance(value, UploadedFile):
            answer.answer_file.save(value.name, value, save=False)
            answer.answer = "file://" + answer.answer_file.name
    else:
        answer.answer = value


def _set_choice_options(answer, options):
    # M2M needs a saved Answer; existing Answers may have stale options.
    if not answer.pk:
        answer.save()
    else:
        answer.options.clear()
    if options:
        answer.options.add(*options)
    answer.answer = ", ".join(str(option) for option in options)
