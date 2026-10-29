# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from unittest.mock import patch

import pytest
from django.core import mail as djmail
from django_scopes import scope

from pretalx.common.exceptions import SendMailException
from pretalx.submission.models.review import Review
from pretalx.submission.tasks import (
    task_export_question_files,
    task_recalculate_review_scores,
    task_send_initial_mails,
)
from tests.factories import (
    CachedFileFactory,
    EventFactory,
    QuestionFactory,
    ReviewFactory,
    SpeakerFactory,
    SubmissionFactory,
    UserFactory,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_task_recalculate_review_scores_delegates_and_skips_missing_event():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    review = ReviewFactory(submission=submission)
    # Bypass save() to set a stale score that doesn't match the empty M2M.
    Review.objects.filter(pk=review.pk).update(score=42)

    assert task_recalculate_review_scores(event_id=99999) is None
    assert Review.objects.get(pk=review.pk).score == 42

    task_recalculate_review_scores(event_id=event.pk)

    assert Review.objects.get(pk=review.pk).score is None


def test_task_export_question_files_skips_missing_question_or_cached_file():
    cached_file = CachedFileFactory()
    question = QuestionFactory()

    assert (
        task_export_question_files(
            question_id=99999, cached_file_id=str(cached_file.id)
        )
        is None
    )
    assert (
        task_export_question_files(
            question_id=question.pk,
            cached_file_id="00000000-0000-0000-0000-000000000000",
        )
        is None
    )
    cached_file.refresh_from_db()
    assert not cached_file.file


def test_task_export_question_files_delegates():
    question = QuestionFactory(variant="file")
    cached_file = CachedFileFactory()

    with (
        patch(
            "pretalx.submission.domain.question.export_answer_files",
            return_value=str(cached_file.id),
        ) as delegate,
        scope(),
    ):
        result = task_export_question_files(
            question_id=question.pk, cached_file_id=str(cached_file.id)
        )

    assert result == str(cached_file.id)
    delegate.assert_called_once_with(question=question, cached_file=cached_file)


def test_task_send_initial_mails_delegates_and_skips_missing_objects():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    user = UserFactory()
    speaker = SpeakerFactory(event=event, user=user)
    submission.speakers.add(speaker)
    djmail.outbox = []

    task_send_initial_mails(submission_id=99999, person_id=user.pk)
    task_send_initial_mails(submission_id=submission.pk, person_id=99999)
    assert djmail.outbox == []

    with scope():
        task_send_initial_mails(submission_id=submission.pk, person_id=user.pk)

    assert [mail.to for mail in djmail.outbox] == [[user.email]]


def test_task_send_initial_mails_handles_send_mail_exception():
    event = EventFactory()
    submission = SubmissionFactory(event=event)
    user = UserFactory()
    speaker = SpeakerFactory(event=event, user=user)
    submission.speakers.add(speaker)

    djmail.outbox = []
    with patch(
        "pretalx.submission.domain.submission.send_initial_mails",
        side_effect=SendMailException("SMTP error"),
    ):
        task_send_initial_mails(submission_id=submission.pk, person_id=user.pk)

    assert djmail.outbox == []
