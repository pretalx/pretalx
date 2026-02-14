# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from django.core.files import File
from django_scopes import scope, scopes_disabled

from pretalx.celery_app import app
from pretalx.common.exceptions import SendMailException
from pretalx.common.models.file import CachedFile
from pretalx.common.text.path import safe_filename
from pretalx.event.models import Event
from pretalx.person.models import User
from pretalx.submission.models import Question, Submission

LOGGER = logging.getLogger(__name__)


@app.task(name="pretalx.submission.recalculate_review_scores")
def recalculate_all_review_scores(*, event_id: int):
    with scopes_disabled():
        event = (
            Event.objects.prefetch_related("submissions").filter(pk=event_id).first()
        )
    if not event:
        LOGGER.error("Could not find Event ID %s for export.", event_id)
        return

    with scope(event=event):
        for submission in event.submissions.all():
            submission.update_review_scores()


@app.task(name="pretalx.submission.export_question_files")
def export_question_files(*, question_id: int, cached_file_id: str):
    with scopes_disabled():
        question = (
            Question.all_objects.select_related("event").filter(pk=question_id).first()
        )
        cached_file = CachedFile.objects.filter(id=cached_file_id).first()

    if not question:
        LOGGER.error("Could not find Question ID %s for file export.", question_id)
        return
    if not cached_file:
        LOGGER.error("Could not find CachedFile ID %s for file export.", cached_file_id)
        return
    if question.variant != "file":
        LOGGER.error("Question %s is not a file question.", question_id)
        return

    event = question.event

    with scope(event=event):
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
                    if not answer.answer_file:
                        continue

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
                    except Exception as e:
                        LOGGER.warning(
                            "Could not read file for answer %s: %s", answer.pk, e
                        )

            with Path(tmp_zip_path).open("rb") as f:
                cached_file.file.save(cached_file.filename, File(f))

        except Exception as e:
            LOGGER.exception("Failed to export question files: %s", e)
            return None

        finally:
            Path(tmp_zip_path).unlink()

    return cached_file_id


@app.task(name="pretalx.submission.send_initial_mails")
def task_send_initial_mails(*, submission_id: int, person_id: int):
    with scopes_disabled():
        submission = Submission.all_objects.filter(pk=submission_id).first()
        person = User.objects.filter(pk=person_id).first()

    if not submission:
        LOGGER.warning(
            "Could not find Submission ID %s for initial mails.", submission_id
        )
        return
    if not person:
        LOGGER.warning("Could not find User ID %s for initial mails.", person_id)
        return

    with scope(event=submission.event):
        try:
            submission.send_initial_mails(person=person)
        except SendMailException as exception:
            LOGGER.warning(str(exception))
