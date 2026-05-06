# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from django.core.files import File
from django.core.files.uploadedfile import UploadedFile

from pretalx.common.text.path import safe_filename
from pretalx.submission.enums import QuestionVariant

LOGGER = logging.getLogger(__name__)


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


def export_answer_files(*, question, cached_file):
    """Bundle every file-typed answer for ``question`` into a zip stored on
    ``cached_file``.

    Returns ``str(cached_file.id)`` on success, or ``None`` if ``question`` is
    not a file question or the zip could not be assembled.
    """
    if question.variant != QuestionVariant.FILE:
        LOGGER.error("Question %s is not a file question.", question.pk)
        return None

    answers = (
        question.answers.filter(answer_file__isnull=False)
        .exclude(answer_file="")
        .select_related("submission", "speaker", "review")
    )

    used_filenames = set()
    tmp_zip_fd, tmp_zip_path = tempfile.mkstemp(suffix=".zip")
    os.close(tmp_zip_fd)

    try:
        with zipfile.ZipFile(tmp_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for answer in answers:
                base_filename = safe_filename(Path(answer.answer_file.name).name)
                filename = base_filename

                counter = 1
                while filename in used_filenames:
                    base_path = Path(base_filename)
                    name, ext = base_path.stem, base_path.suffix
                    filename = f"{name}_{counter}{ext}"
                    counter += 1

                used_filenames.add(filename)

                try:
                    with (
                        zf.open(filename, "w") as dest,
                        answer.answer_file.open("rb") as src,
                    ):
                        shutil.copyfileobj(src, dest)
                except OSError as e:
                    LOGGER.warning(
                        "Could not read file for answer %s: %s", answer.pk, e
                    )

        with Path(tmp_zip_path).open("rb") as f:
            cached_file.file.save(cached_file.filename, File(f))

    except Exception:
        LOGGER.exception("Failed to export question files")
        return None

    finally:
        Path(tmp_zip_path).unlink()

    return str(cached_file.id)
