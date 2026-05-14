# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import logging

from django_scopes import scope, scopes_disabled

from pretalx.celery_app import app
from pretalx.common.exceptions import SendMailException

LOGGER = logging.getLogger(__name__)


@app.task(name="pretalx.submission.recalculate_review_scores")
def task_recalculate_review_scores(*, event_id: int):
    from pretalx.event.models import Event  # noqa: PLC0415 -- leaf
    from pretalx.submission.domain.review import (  # noqa: PLC0415 -- leaf
        recalculate_event_scores,
    )

    with scopes_disabled():
        event = Event.objects.filter(pk=event_id).first()
    if not event:
        LOGGER.error("Could not find Event ID %s for review recalculation.", event_id)
        return

    with scope(event=event):
        recalculate_event_scores(event)


@app.task(name="pretalx.submission.export_question_files")
def task_export_question_files(*, question_id: int, cached_file_id: str):
    from pretalx.common.models.file import CachedFile  # noqa: PLC0415 -- leaf
    from pretalx.submission.domain.question import (  # noqa: PLC0415 -- leaf
        export_answer_files,
    )
    from pretalx.submission.models import Question  # noqa: PLC0415 -- leaf

    with scopes_disabled():
        question = (
            Question.all_objects.select_related("event").filter(pk=question_id).first()
        )
        cached_file = CachedFile.objects.filter(id=cached_file_id).first()

    if not question:
        LOGGER.error("Could not find Question ID %s for file export.", question_id)
        return None
    if not cached_file:
        LOGGER.error("Could not find CachedFile ID %s for file export.", cached_file_id)
        return None

    with scope(event=question.event):
        return export_answer_files(question=question, cached_file=cached_file)


@app.task(name="pretalx.submission.send_initial_mails")
def task_send_initial_mails(*, submission_id: int, person_id: int):
    from pretalx.person.models import User  # noqa: PLC0415 -- leaf
    from pretalx.submission.domain.submission import (  # noqa: PLC0415 -- leaf
        send_initial_mails,
    )
    from pretalx.submission.models import Submission  # noqa: PLC0415 -- leaf

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
            send_initial_mails(submission, person=person)
        except SendMailException as exception:
            LOGGER.warning(str(exception))
